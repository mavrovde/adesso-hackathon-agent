# CLAUDE.md

This file teaches Claude Code how to work in this repository.

## Project

**adesso-hackathon-agent** — IT Helpdesk triage agent built on the Claude Agent SDK.
Hackathon Scenario 5: "The Intake". Inbound IT requests are classified, enriched, and routed autonomously. Routine cases (e.g. password resets) are auto-resolved; high-risk actions require human approval.

See `TASK.md` for the full scenario description.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

## Run

```bash
# Single request
python -m agent.main --input "My laptop won't connect to WiFi"

# Full eval harness
python -m eval.run

# Adversarial eval only
python -m eval.run --suite adversarial
```

## Architecture

```
Inbound request (text)
        │
        ▼
┌─────────────────────┐
│  Coordinator Agent  │  classify · enrich · route
│                     │  validation-retry loop (max 3 retries)
└──────────┬──────────┘
           │  explicit context in Task prompt
     ┌─────┴──────┐
     ▼            ▼
┌──────────┐  ┌──────────────┐
│ Password │  │ IT Specialist│
│  Reset   │  │    Agent     │
│  Agent   │  └──────────────┘
└──────────┘
     │
     ▼
PreToolUse hook → hard block on high-risk patterns
     │
     ▼
Human-in-the-loop (escalation rules)
```

**Key rules:**
- Specialist subagents do NOT inherit coordinator context — pass everything needed in the Task prompt
- Max 4–5 tools per specialist (tool-selection reliability drops past that)
- All tool errors return `{"isError": true, "reason": "...", "guidance": "..."}` — never raw strings
- Escalation rules are explicit: `category + confidence < threshold + dollar_impact` — never vague

## Project Structure

```
agent/
  main.py           # entry point, coordinator loop
  coordinator.py    # classification, enrichment, routing + validation-retry
  specialists/
    password_reset.py
    it_specialist.py
  tools/            # one file per tool
  hooks.py          # PreToolUse hard blocks
eval/
  run.py            # eval harness
  datasets/
    normal.json     # labeled normal traffic
    adversarial.json # prompt injection, ambiguous urgency, hidden exposure
```

## Conventions

- **Structured output always**: coordinator returns typed dicts, never free text
- **Log reasoning chains**: every routing decision must be replayable from the log alone — log `category`, `confidence`, `routing`, `reasoning`, `requires_human`, `retry_count`
- **Explicit escalation rules** (not "when unsure"):
  - `category in ["legal", "compliance", "vip"]` → escalate
  - `confidence < 0.75` → escalate
  - `dollar_impact > 10_000` → escalate
- **PreToolUse hard blocks**: `frozen_account + write_action`, `pii_detected in route_target`, `known_bad_route`
- No mocking in tests — use the real SDK with a test API key

## Hackathon Deliverables

Three files matter for judging:
1. `README.md` — what was built and how to run it
2. `CLAUDE.md` — how the team taught Claude to work their way (this file)
3. `presentation.html` — the demo story

Commit history is evidence — commit often, with meaningful messages.

## Domain: IT Helpdesk

**Categories:** `password_reset` · `network` · `software` · `hardware` · `access` · `vip_escalation` · `unknown`

**Priority levels:** P1 (critical/outage) · P2 (major) · P3 (minor) · P4 (routine)

**Auto-resolve:** password resets where account is active and not flagged

**Always escalate:** VIP users, legal/compliance mentions, confidence < 0.75, any write action on a flagged account
