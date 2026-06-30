# CLAUDE.md

IT Helpdesk triage agent (adesso-hackathon-agent) built on the Claude Agent SDK.

## Task Tracking

Open tasks are tracked in [`TODO.md`](TODO.md).

> **Rule:** Set tasks to `🔄 In Progress` when you start, `✅ Done` when complete. Never delete tasks — only update status.

## Commands

```bash
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here

python -m agent.main --input "My laptop won't connect to WiFi"
python -m eval.run
python -m eval.run --suite adversarial

ruff check . && ruff format .
mypy --strict .
pytest
```

## Architecture Constraints

**Tool design:** Max 4–5 tools per specialist agent. Tools must never raise unhandled exceptions — always return:
```python
{"ok": True, "data": {...}}                  # success
{"ok": False, "isError": True, "code": "...", "guidance": "..."}  # failure
```

**Validation retry:** Wrap Pydantic output parsing in a retry loop. `MAX_RETRIES = 3`, then escalate to human. Log `retry_count` and `error_type` per request.

**Specialist handoff:** Subagents are stateless — they do not inherit coordinator context. Pass everything explicitly: original request, category, priority (P1–P4), user context, KB snippets, ticket ID.

**PreToolUse hard blocks** (deterministic, not prompt-based):
- Block write tools on `FROZEN` / `UNDER_INVESTIGATION` accounts.
- Block `resolve_ticket` on P1 issues.
- Block any call containing prompt-injection or PII exfiltration patterns.

**Human escalation triggers:**
- Confidence < `0.75`
- User is VIP (C-Level/Board/whitelist)
- Legal/compliance mention (GDPR, Datenschutz, lawsuit)
- Estimated business impact > €10,000
- P1/P2 incident + any write tool

**Auto-resolution:** Only `password_reset` on active, unflagged accounts via SSO.

## Python Rules (non-obvious)

- `from __future__ import annotations` at the top of every file.
- No `print()` in production paths — use `logging.getLogger(__name__)` with JSON format.
- Scrub PII (emails, names, passwords) from all log output.
- Log these fields per routing decision: `request_id`, `channel`, `category`, `confidence`, `routing_target`, `retry_count`, `error_type`, `escalated`, `hook_blocked`.
- No bare `except:` — catch specific exceptions.
- `X | None` not `Optional[X]`. No `Any`. Use `TypedDict` or `pydantic.BaseModel` for cross-module data.
- Integration tests must hit the real Claude API — do not mock it.
