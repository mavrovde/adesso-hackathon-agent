# IT Helpdesk Agent — Implementation Plan

## Scenario

**Domain:** IT helpdesk  
**Inputs:** Tickets, chat messages, "urgent" emails to the CIO  
**Decisions:** P1–P4 priority classification, queue routing, auto-resolve password resets

---

## What the Agent Does (The Mandate)

| Decision | Who decides |
|---|---|
| Classify priority P1–P4 | Coordinator (automated) |
| Route to queue (network, software, hardware, security, access) | Coordinator (automated) |
| Auto-resolve password resets | PasswordResetSpecialist (automated) |
| Auto-resolve known low-risk issues with KB match | IncidentSpecialist (automated, P3/P4 only) |
| Any write action on P1/P2 incidents | Human approval required |
| Anything touching a flagged/frozen account | Hard block via PreToolUse hook |

**Deliberately NOT automated:**
- Termination-related access revocations (legal risk)
- Anything the user classifies as a security breach (escalate only, no auto-action)
- Actions on accounts flagged as under investigation

---

## Architecture

### Agent Loop

```
Incoming request
      │
      ▼
 Coordinator Agent
  ├─ classify priority (P1–P4)
  ├─ enrich with user context
  ├─ determine category (password, hardware, software, network, security, access)
  ├─ log reasoning chain
  └─ route to subagent via Task
         │
         ├──▶ PasswordResetSpecialist  (category = "password_reset")
         │
         └──▶ IncidentSpecialist       (all other categories)
                    │
                    ▼
              structured output
              (ticket_id, priority, queue, action_taken, escalated, reasoning)
```

**Key SDK notes:**
- Task subagents do NOT inherit the coordinator's context — all relevant fields (ticket body, user context, priority, category) are passed explicitly in each Task prompt.
- `stop_reason` handled: `end_turn` → log and return; `tool_use` → execute tool; `max_tokens` → log truncation warning and retry with shorter context.

### Coordinator → Subagent context handoff

Each Task prompt includes:
- Original request text
- Classified priority and category
- User context (role, department, history)
- Relevant KB snippets (pre-fetched by coordinator)
- Ticket ID

---

## Tools

### PasswordResetSpecialist tools (4)

| Tool | Purpose |
|---|---|
| `get_user_context(user_id)` | Look up user's role, department, account status, recent tickets |
| `lookup_kb(query)` | Search knowledge base for reset procedures per system |
| `reset_user_password(user_id, system)` | Execute the reset; returns new temporary credential delivery method |
| `resolve_ticket(ticket_id, resolution_summary)` | Close ticket with audit trail |

### IncidentSpecialist tools (5)

| Tool | Purpose |
|---|---|
| `get_user_context(user_id)` | Same as above |
| `lookup_kb(query)` | Search for known issues and runbooks |
| `create_or_update_ticket(...)` | Write ticket with priority, queue, and classification |
| `resolve_ticket(ticket_id, resolution_summary)` | Auto-close when KB match is unambiguous and priority is P3/P4 |
| `escalate(ticket_id, reason, severity, impact)` | Trigger human-in-the-loop with full context |

All tools return structured responses:
- Success: `{ ok: true, data: {...} }`
- Failure: `{ ok: false, isError: true, code: "ACCOUNT_FROZEN" | "USER_NOT_FOUND" | ..., guidance: "..." }`

---

## Human-in-the-Loop (The Brake)

**Escalation rules (explicit, not vague):**
- Priority P1 + any write action → require human approval
- Priority P2 + `reset_user_password` or `resolve_ticket` → require human approval
- Confidence < 0.7 on category classification → escalate, do not route
- Any ticket mentioning "breach", "ransomware", "exfil" → escalate immediately, no auto-action

**`PreToolUse` hard blocks (deterministic, not model-driven):**
- `reset_user_password` where account status = `FROZEN` or `UNDER_INVESTIGATION`
- `resolve_ticket` where priority = `P1`
- Any tool call where request body matches known prompt-injection patterns

---

## Implementation Order

1. **The Mandate** — this document's "What the Agent Does" section ✓
2. **The Bones** — ADR with architecture diagram (above)
3. **The Tools** — implement tools with mock ticketing system (in-memory dict)
4. **The Triage** — coordinator agent with classification, logging, and validation-retry loop
5. **The Brake** — `PreToolUse` hook + escalation rules

---

## Tech Stack

- **Language:** Python (Claude Agent SDK)
- **Ticketing system:** Mocked in-memory for the hackathon
- **Auth:** `ANTHROPIC_API_KEY` env var
