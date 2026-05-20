"""Wired mock provider for M1 tests — Phase 7.0: mode-aware canned responses."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.llm.base import LLMRequest, LLMResponse

_VALID_MODES = frozenset({"bare", "reflection", "narrative", "judge"})

# Reuse citation marker pattern (mirrors app/narrative/citation.py)
_MARKER_RE = re.compile(r"\[↑e([0-9a-f]{8})\]")

_REFLECTION_JSON = (
    '{"summary":"mock 반성 요약","descriptors":["관찰형","정기적"],"evidence_event_ids":[]}'
)
_JUDGE_JSON = '{"is_grounded": true, "reason": "mock judge — assumed grounded"}'


@dataclass(frozen=True)
class MockProvider:
    name: str = "mock"
    model: str = "mock-1"
    mode: str = "bare"

    def __post_init__(self) -> None:
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"MockProvider: unknown mode '{self.mode}'. "
                f"Valid: {sorted(_VALID_MODES)}"
            )

    async def complete(self, req: LLMRequest) -> LLMResponse:
        text = self._build_text(req.prompt)
        return LLMResponse(
            text=text,
            model=self.model,
            tier=req.tier,
            input_tokens=len(req.prompt.split()),
            output_tokens=len(text.split()),
        )

    def _build_text(self, prompt: str) -> str:
        if self.mode == "bare":
            return "[mock]"
        if self.mode == "reflection":
            return _REFLECTION_JSON
        if self.mode == "judge":
            return _JUDGE_JSON
        if self.mode == "narrative":
            return self._build_narrative(prompt)
        # Should never reach here due to __post_init__ guard
        raise ValueError(f"MockProvider: unhandled mode '{self.mode}'")

    @staticmethod
    def _build_narrative(prompt: str) -> str:
        """Extract up to 3 [↑e<sid>] markers from prompt and cite them."""
        matches = _MARKER_RE.findall(prompt)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for sid in matches:
            if sid not in seen:
                seen.add(sid)
                unique.append(sid)
            if len(unique) == 3:
                break

        if not unique:
            return "증거가 부족합니다."

        cited = " ".join(f"[↑e{sid}]" for sid in unique)
        return f"agent 활동이 관찰되었습니다 {cited}."
