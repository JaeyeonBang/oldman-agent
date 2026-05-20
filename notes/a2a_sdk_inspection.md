# a2a-sdk Inspection Notes (v1.0.3)

Generated: 2026-05-20 during Phase 6.2 of v1.0.1 plan debt resolution.

## Install outcome

**SUCCESS** — `a2a-sdk==1.0.3` installed cleanly via `uv pip install 'a2a-sdk>=1.0,<2.0'`.

## AgentCard location

Two AgentCard types exist in the package:

| Module | Type | System | Notes |
|--------|------|--------|-------|
| `a2a.types` | `AgentCard` (protobuf) | `google.protobuf` MessageMeta | No `url` top-level field; `url` lives inside `provider.url`. Not suitable for our JSON response validation. |
| `a2a.compat.v0_3.types` | `AgentCard` (pydantic v2) | pydantic v2 BaseModel | Has `url` as top-level required field matching A2A v0.2 public spec. **This is the type we use.** |

**Import used in contract test:**
```python
from a2a.compat.v0_3.types import AgentCard as A2AAgentCard
```

## AgentCard required fields (compat pydantic v2)

| Python name | Alias (JSON key) | Type | Required |
|-------------|-----------------|------|---------|
| `name` | `name` | `str` | Yes |
| `description` | `description` | `str` | Yes |
| `url` | `url` | `str` | Yes |
| `version` | `version` | `str` | Yes |
| `capabilities` | `capabilities` | `AgentCapabilities` | Yes |
| `default_input_modes` | `defaultInputModes` | `list[str]` | Yes |
| `default_output_modes` | `defaultOutputModes` | `list[str]` | Yes |
| `skills` | `skills` | `list[AgentSkill]` | Yes |

Optional fields: `provider`, `documentation_url`, `security`, `security_schemes`, `protocol_version`, `icon_url`, `additional_interfaces`, `preferred_transport`, `supports_authenticated_extended_card`, `signatures`.

## AgentCapabilities fields

| Python name | Alias | Type | Required |
|-------------|-------|------|---------|
| `streaming` | `streaming` | `bool \| None` | No |
| `push_notifications` | `pushNotifications` | `bool \| None` | No |
| `state_transition_history` | `stateTransitionHistory` | `bool \| None` | No |
| `extensions` | `extensions` | `list[AgentExtension] \| None` | No |

## AgentSkill fields

| Python name | Alias | Type | Required |
|-------------|-------|------|---------|
| `id` | `id` | `str` | Yes |
| `name` | `name` | `str` | Yes |
| `description` | `description` | `str` | Yes |
| `tags` | `tags` | `list[str]` | Yes |
| `examples` | `examples` | `list[str] \| None` | No |
| `input_modes` | `inputModes` | `list[str] \| None` | No |
| `output_modes` | `outputModes` | `list[str] \| None` | No |
| `security` | `security` | `list[dict] \| None` | No |

## Type system

**pydantic v2** — `AgentCard` is a `BaseModel` subclass. Validation via `model_validate()`.
Uses camelCase aliases for JSON serialisation (`populate_by_name=True` implied by `A2ABaseModel`).

## Vendor extension support

The compat pydantic `AgentCard` does **not** have `model_config = ConfigDict(extra="allow")` — it inherits from `A2ABaseModel`. Extra fields are **not** automatically allowed. However, `model_validate()` with `strict=False` (default) will succeed on a dict that includes extra keys like `"x-oldman"` as long as the model doesn't enforce `extra="forbid"`.

**Decision**: Our `/agent-card` response includes `"x-oldman"` as an extra key in the serialised dict. The SDK `model_validate()` will strip it silently (not raise). The contract test verifies `"x-oldman"` survives in the raw `resp.json()` dict (which it does — it's our serialisation, not the SDK's).

## Conclusion

- Use `from a2a.compat.v0_3.types import AgentCard as A2AAgentCard` in contract test.
- Our pydantic schemas in `app/api/schemas.py` mirror this field set directly.
- The `url` field is top-level in the compat type — matches A2A v0.2 public spec.
- `x-oldman` vendor extension is carried in our own serialised dict; contract test checks it in `raw`, not in the SDK-validated object.
