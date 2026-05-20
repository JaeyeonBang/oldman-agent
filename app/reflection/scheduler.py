"""Reflection scheduler — Phase 2.4.

트리거 조건 평가 + LLM 호출 + reflections 행 + entities_semantic.traits_json 업데이트.
모든 단계는 단일 DuckDB 트랜잭션 안에서 수행.

§10 Q2 결정에 따라 LLM 예외는 swallow + log → publish 흐름 보호.

⚠️ 이 파일은 CLAUDE.md EVAL 트리거 대상. 변경 시 EVAL-1 재실행 필요.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
from pydantic import ValidationError

from app.llm.base import LLMRequest, LLMTier
from app.reflection.output_schema import TraitsCompiled
from app.reflection.prompts import build_user_message, load_prompt
from app.reflection.state import get_trigger_state
from app.reflection.traits_compile import apply_traits, merge_traits

_LOG = logging.getLogger(__name__)

# v1.0.5: ```json ... ``` 또는 ``` ... ``` 코드 펜스를 벗기는 regex.
# DOTALL로 multi-line 매칭. 펜스 안의 raw 텍스트만 캡처.
_CODE_FENCE_RE = re.compile(
    r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL,
)


def _strip_code_fences(text: str) -> str:
    """LLM 응답에서 markdown 코드 fence를 제거하고 raw 텍스트만 반환한다.

    예:
        ``"```json\\n{...}\\n```"`` → ``"{...}"``
        ``"{...}"`` → ``"{...}"`` (변동 없음)
    """
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped

_DEFAULT_COUNT_THRESHOLD = 10
_DEFAULT_AGE_THRESHOLD = timedelta(hours=6)
_DEFAULT_EVENTS_FOR_CONTEXT = 10

# (scope, subject) 별 concurrent 호출 시 직렬화용 lock.
# 같은 키에 대해 동시에 여러 publish가 트리거되면 둘 다 reflection을 생성
# 하지 않도록 한다 (데모 스케일에서는 중복 허용이나, lock으로 줄임).
_locks: dict[tuple[str, str], asyncio.Lock] = {}


def _get_lock(scope: str, subject: str) -> asyncio.Lock:
    key = (scope, subject)
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


from app.reflection.state import ReflectionTriggerState  # noqa: E402


def should_trigger(
    state: ReflectionTriggerState,
    *,
    now: datetime,
    count_threshold: int = _DEFAULT_COUNT_THRESHOLD,
    age_threshold: timedelta = _DEFAULT_AGE_THRESHOLD,
) -> bool:
    """반성 트리거 조건 평가.

    트리거 조건 (OR):
    1. 이벤트 카운트 ≥ count_threshold
    2. 마지막 reflection으로부터 age_threshold 이상 경과 AND 이벤트 ≥ 1
       (이벤트가 0이면 반성할 내용 없음 → false)
    """
    if state.events_since_last_reflection >= count_threshold:
        return True

    if state.events_since_last_reflection >= 1 and state.last_reflection_ts is not None:
        last_ts = state.last_reflection_ts
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)
        elapsed = now - last_ts
        if elapsed >= age_threshold:
            return True

    return False


def _fetch_recent_events(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str,
    subject: str,
    n: int,
) -> list[dict[str, Any]]:
    """scope/subject에 해당하는 최근 n개 이벤트를 시간 오름차순으로 반환."""
    if scope == "agent":
        rows = conn.execute(
            "SELECT event_id, kind, payload_json, ts FROM events "
            "WHERE source_agent = ? "
            "ORDER BY ts DESC LIMIT ?",
            [subject, n],
        ).fetchall()
    elif scope == "pair":
        observer, observed = subject.split(":", 1)
        rows = conn.execute(
            "SELECT e.event_id, e.kind, e.payload_json, e.ts "
            "FROM entities_episodic ep "
            "JOIN events e ON e.event_id = ep.event_id "
            "WHERE ep.observer_agent = ? AND ep.observed_agent = ? "
            "ORDER BY e.ts DESC LIMIT ?",
            [observer, observed, n],
        ).fetchall()
    elif scope == "society":
        rows = conn.execute(
            "SELECT event_id, kind, payload_json, ts FROM events "
            "ORDER BY ts DESC LIMIT ?",
            [n],
        ).fetchall()
    else:
        raise ValueError(f"알 수 없는 scope: {scope!r}")

    # 시간 오름차순 (오래된 → 최근)
    rows = list(reversed(rows))
    out: list[dict[str, Any]] = []
    for event_id, kind, payload_json, _ts in rows:
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            payload = {}
        out.append({"event_id": str(event_id), "kind": kind, "payload": payload})
    return out


async def maybe_run_reflection(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str,
    subject: str,
    provider: Any,
    now: datetime | None = None,
    count_threshold: int = _DEFAULT_COUNT_THRESHOLD,
    age_threshold: timedelta = _DEFAULT_AGE_THRESHOLD,
    n_context_events: int = _DEFAULT_EVENTS_FOR_CONTEXT,
) -> TraitsCompiled | None:
    """트리거 조건 검사 후 필요시 reflection 생성.

    Args:
        conn: DuckDB 연결.
        scope: 'agent' | 'pair' | 'society'
        subject: scope별 식별자.
        provider: LLMProvider 호환 객체 (`complete(LLMRequest) -> LLMResponse`).
        now: 현재 시각 (테스트 주입). 기본 datetime.now(UTC).

    Returns:
        성공 시 TraitsCompiled, 아니면 None.

    Note:
        LLM/파싱/DB 예외는 모두 swallow + log → publish 흐름 보호.
    """
    actual_now = now or datetime.now(UTC)

    async with _get_lock(scope, subject):
        # 1. trigger state 평가
        state = get_trigger_state(conn, scope=scope, subject=subject)
        if not should_trigger(
            state,
            now=actual_now,
            count_threshold=count_threshold,
            age_threshold=age_threshold,
        ):
            return None

        # 2. 프롬프트 + 컨텍스트 이벤트 로드
        try:
            system, _ = load_prompt(scope)
        except Exception as exc:
            _LOG.warning("reflection: load_prompt 실패 (scope=%s): %s", scope, exc)
            return None

        events = _fetch_recent_events(
            conn, scope=scope, subject=subject, n=n_context_events
        )
        if not events:
            _LOG.info(
                "reflection: 컨텍스트 이벤트 없음 (scope=%s subject=%s)",
                scope,
                subject,
            )
            return None

        user_msg = build_user_message(events, n=n_context_events)

        # 3. LLM 호출 (예외 swallow)
        try:
            response = await provider.complete(
                LLMRequest(
                    system=system,
                    prompt=user_msg,
                    tier=LLMTier.CHEAP,
                    max_tokens=1024,
                )
            )
        except Exception as exc:
            _LOG.warning(
                "reflection: LLM 호출 실패 (scope=%s subject=%s): %s",
                scope,
                subject,
                exc,
            )
            return None

        # 4. 응답 파싱 + 검증 — v1.0.5: 일부 LLM(DeepSeek 등)이 ```json ... ```
        # markdown 코드 fence로 감싸 응답하므로 파싱 전에 fence를 제거한다.
        try:
            parsed = TraitsCompiled.model_validate_json(_strip_code_fences(response.text))
        except ValidationError as exc:
            _LOG.warning(
                "reflection: LLM 응답 파싱 실패 (scope=%s subject=%s): %s",
                scope,
                subject,
                exc,
            )
            return None
        except Exception as exc:
            _LOG.warning(
                "reflection: LLM 응답 처리 실패 (scope=%s subject=%s): %s",
                scope,
                subject,
                exc,
            )
            return None

        # 5. DB 트랜잭션: reflections insert + traits_json update
        try:
            _persist_reflection(
                conn,
                scope=scope,
                subject=subject,
                now=actual_now,
                parsed=parsed,
                events=events,
            )
        except Exception as exc:
            _LOG.warning(
                "reflection: DB persist 실패 (scope=%s subject=%s): %s",
                scope,
                subject,
                exc,
            )
            with contextlib.suppress(duckdb.Error):
                conn.execute("ROLLBACK")
            return None

        return parsed


def _persist_reflection(
    conn: duckdb.DuckDBPyConnection,
    *,
    scope: str,
    subject: str,
    now: datetime,
    parsed: TraitsCompiled,
    events: list[dict[str, Any]],
) -> None:
    """reflection 행 + (scope ∈ {agent,pair}) traits_json 머지를 단일 트랜잭션으로 수행."""
    reflection_id = str(uuid.uuid4())
    source_event_ids = [e["event_id"] for e in events]
    if events:
        # ts는 fetch_recent_events 단계에서 빠졌으므로 보수적으로 now 기준 30분 윈도우
        event_range_start = now - timedelta(hours=1)
        event_range_end = now
    else:
        event_range_start = now
        event_range_end = now

    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO reflections "
            "(reflection_id, ts, scope, subject, text, "
            " event_range_start, event_range_end, source_event_ids) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                reflection_id,
                now,
                scope,
                subject,
                parsed.summary,
                event_range_start,
                event_range_end,
                json.dumps(source_event_ids),
            ],
        )

        # scope=agent 일 때 traits_json 업데이트.
        # scope=pair는 subject 형식이 "observer:observed"라 두 에이전트 모두 업데이트.
        if scope == "agent":
            existing = _load_traits(conn, subject)
            merged = merge_traits(existing, parsed)
            apply_traits(conn, agent_id=subject, traits=merged, now=now)
        elif scope == "pair":
            observer, observed = subject.split(":", 1)
            for aid in (observer, observed):
                existing = _load_traits(conn, aid)
                merged = merge_traits(existing, parsed)
                apply_traits(conn, agent_id=aid, traits=merged, now=now)
        # scope=society 는 글로벌 reflections에만 기록, traits 업데이트 없음

        conn.execute("COMMIT")
    except Exception:
        with contextlib.suppress(duckdb.Error):
            conn.execute("ROLLBACK")
        raise


def _load_traits(
    conn: duckdb.DuckDBPyConnection, agent_id: str
) -> dict[str, Any]:
    """entities_semantic.traits_json을 dict으로 로드. 행 없으면 빈 dict."""
    row = conn.execute(
        "SELECT traits_json FROM entities_semantic WHERE agent_id = ?",
        [agent_id],
    ).fetchone()
    if row is None or row[0] is None:
        return {}
    try:
        loaded = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return loaded if isinstance(loaded, dict) else {}
    except json.JSONDecodeError:
        return {}
