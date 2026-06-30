# CLAUDE.md

This file teaches Claude Code how to work in this repository. It defines our development workflows, Python best practices, and Claude Agent SDK integration patterns.

---

## Project Overview

**adesso-hackathon-agent** — An IT Helpdesk triage and intake agent built on the [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview).
It automates classification, context enrichment, queue routing, and password-reset auto-resolution, while applying deterministic security hooks (`PreToolUse`) and explicit business escalation rules for human-in-the-loop validation.

---

## Setup and Run

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (pinned versions)
pip install -r requirements.txt
# (Optional) Install development dependencies if separate
# pip install -r requirements-dev.txt

# Set Anthropic API Key
export ANTHROPIC_API_KEY=your_key_here
```

### Execution Commands
```bash
# Run the coordinator agent with a single input
python -m agent.main --input "My laptop won't connect to WiFi"

# Run the full evaluation harness
python -m eval.run

# Run only the adversarial evaluation suite
python -m eval.run --suite adversarial

# Run code style, linting, and type checking (suggested)
ruff check .
ruff format .
mypy --strict .
pytest
```

---

## Project Structure

```
.
├── CLAUDE.md              # Claude Code workspace guidelines (this file)
├── MANDATE.md             # PM/BA Mandate defining agent authority & boundaries
├── PLAN.md                # IT Helpdesk Agent implementation plan
├── README.md              # Project setup, execution, and architecture overview
├── TASK.md                # Original hackathon scenario description
├── agent/
│   ├── main.py            # Entry point, CLI parser, main loop
│   ├── coordinator.py     # Coordinator agent (classification, enrichment, routing)
│   ├── hooks.py           # PreToolUse permission hooks (hard blocks)
│   ├── human_feedback.py  # Human override loop and feedback learning helpers
│   ├── specialists/       # Stateless subagents
│   │   ├── __init__.py
│   │   ├── password_reset.py
│   │   └── it_specialist.py
│   └── tools/             # Specialist custom tools
│       ├── __init__.py
│       ├── access.py
│       ├── kb.py
│       └── ticket.py
└── eval/
    ├── run.py             # Evaluation harness
    └── datasets/
        ├── normal.json    # Labeled normal traffic dataset
        └── adversarial.json # Labeled prompt injection / edge cases dataset
```

---

## Claude Agent SDK & Architecture Best Practices

All development relating to the Claude Agent SDK must adhere to the following architectural guidelines:

### 1. Agent Loop & `stop_reason` Handling
- Do not let the SDK handle loop execution blindly. Always handle `stop_reason` explicitly in custom loops:
  - `stop_reason == "tool_use"`: Resolve the tool call via local dispatcher, feed the output back to the model, and continue.
  - `stop_reason == "end_turn"`: The model has finished its reasoning. Capture the output, parse the decision, log, and exit.
  - `stop_reason == "max_tokens"`: Log a truncation warning, notify the user, and truncate context or retry with a compressed history.

### 2. Coordinator & Specialist Handoff
- **Context Isolation:** Specialist subagents (e.g., `PasswordResetAgent`, `ITSpecialistAgent`) are stateless and **do not** inherit the coordinator's prompt context.
- **Explicit Prompt Handoff:** All required information must be explicitly passed to the subagent via the `Task` prompt, including:
  - Original request text.
  - Prioritized category and urgency (P1–P4).
  - User context (role, department, status, VIP status).
  - Pre-fetched knowledge base (KB) snippets.
  - Ticketing metadata (ticket ID).

### 3. Custom Tool Design
- **Tool Discipline:** Restrict each specialist agent to **4 to 5 tools** max. Tool selection accuracy drops significantly when the tool space is bloated.
- **Systematic Tool Descriptions:** Every tool definition must include a detailed docstring specifying:
  - Clear parameters and types.
  - What the tool does and, critically, **what it does NOT do**.
  - Expected inputs and edge cases.
  - Typical query examples.
- **Structured Error Responses:** Tools must **never** raise unhandled exceptions or return raw strings to the agent on failure. They must return a structured payload for Claude to recover:
  ```python
  # Success
  {"ok": True, "data": {...}}
  # Failure
  {"ok": False, "isError": True, "code": "USER_NOT_FOUND", "guidance": "Verify user ID and try again."}
  ```

### 4. Validation-Retry Loop
- Wrap the coordinator's structured JSON/Pydantic output parsing in a retry loop.
- If parsing or validation fails (e.g. `pydantic.ValidationError`), capture the specific validation error details and feed them back into the next model turn.
- Limit retries to `MAX_RETRIES = 3`. If the model fails 3 times, escalate to a human.
- Log retry counts and validation error types per request.

### 5. Deterministic Guardrails ("The Brake")
- **Deterministic Hard Blocks (`PreToolUse` Hook):**
  - Implement deterministic hooks that execute **before** Claude calls a tool. Do not rely on model-driven system prompts for safety.
  - Prohibit actions on frozen or investigated accounts (e.g. `reset_user_password` where status is `FROZEN` or `UNDER_INVESTIGATION`).
  - Prohibit any write actions on critical issues (e.g. `resolve_ticket` on P1 issues).
  - Prohibit any tool call containing suspected prompt-injection vectors or exfiltration patterns (PII leakage).
- **Explicit Escalation Rules (Human-in-the-Loop):**
  - Route to human when confidence threshold < `0.75`.
  - Route to human when user is a VIP (C-Level/Board or whitelisted).
  - Route to human when request body mentions legal/compliance terms (Datenschutz, GDPR, lawsuit).
  - Route to human when estimated business impact > €10,000.
  - Route to human on priority P1/P2 incidents for any writing tools.

### 6. Human Feedback Loop
- When a human overrides the agent, capture the override decision.
- Save the override as a labeled example to feed back into the eval dataset or to use as few-shot prompt examples for the classifier.

---

## Python Best Practices

Follow these standard coding and design patterns across the codebase:

### Style, Formatting, and Linting
- **Python Version:** Target **Python 3.11+**.
- **Code Style:** Max line length is **100 characters**.
- **Linter & Formatter:** Use **`ruff`** for formatting and linting. Run `ruff check .` and `ruff format .` before committing.
- **Naming Conventions:**
  - `snake_case` for variables, functions, and modules.
  - `PascalCase` for classes and Pydantic models.
  - `UPPER_SNAKE_CASE` for global/module constants.
- **Robust Syntax:**
  - Prefer f-strings for string interpolation.
  - No bare `except:`. Always catch specific exceptions (e.g., `except ValueError:`).
  - Never use mutable default arguments (`def f(x=[]):`). Use `x: list | None = None` and initialize inside the function.

### Type Annotations
- Use `from __future__ import annotations` at the top of every python file.
- Annotate all function parameters and return types. Avoid the `Any` type.
- Use Python 3.10+ native union syntax (`X | None` instead of `Optional[X]`).
- Use `TypedDict` or `pydantic.BaseModel` for structured data crossing module boundaries (no raw `dict` structures for complex data structures).
- Run `mypy --strict .` to verify type safety.

### Imports
- Organize imports in three groups: stdlib, third-party libraries, and local packages, separated by blank lines.
- Use absolute imports (e.g., `from agent.tools.kb import search_kb`).
- Never use wildcard imports (`from module import *`).

### Logging and PII Security
- Use structured logging (JSON format) via `logging.getLogger(__name__)`.
- **No Production Prints:** Do not use `print()` in core production paths.
- **PII Scrubbing:** Ensure all logs are scrubbed of PII (emails, names, passwords) before writing.
- **Decision Traceability:** Log fields per routing decision: `request_id`, `channel`, `category`, `confidence`, `routing_target`, `retry_count`, `error_type`, `escalated`, `hook_blocked`.

### Asynchronous Programming
- Use `async` and `await` throughout.
- Avoid calling `asyncio.run()` in places with active event loops.
- Set explicit, non-blocking timeouts (e.g., using `asyncio.wait_for`) on all network, API, or system-of-record requests.

### Testing
- Use `pytest` and `pytest-asyncio` for unit and integration testing.
- Do not mock the Claude API in integration tests; use a valid test environment `ANTHROPIC_API_KEY`.
- Mock external ticketing systems and system-of-record APIs using mock objects or in-memory dicts.
- Write tests for every custom tool covering:
  - The happy path.
  - The structured-error path.
  - Edge cases and invalid inputs.

---

## Domain & Incident Conventions (IT Helpdesk)

Ensure these constants and conventions are respected:

- **Incident Categories:** `password_reset`, `network`, `software`, `hardware`, `access`, `vip_escalation`, `unknown`.
- **Priority Levels:**
  - `P1`: Critical / Outage (Always escalates write tools).
  - `P2`: Major (Escalates major write/resolve tools).
  - `P3`: Minor (Can be resolved via IncidentSpecialist with KB match).
  - `P4`: Routine (Auto-resolution candidate).
- **Auto-Resolution Candidates:** Only `password_reset` category on active, unflagged accounts via SSO channels.
- **Escalation Triggers:**
  - Confidence score < `0.75`
  - Language is not English or German.
  - VIP Role or VIP whitelist.
  - High dollar impact (> €10,000).
  - Legal or compliance mentions (e.g. GDPR, Datenschutz).

---

## Evaluation Scorecard Metrics

Our CI-based eval harness calculates the following metrics over a stratified sample of normal (`eval/datasets/normal.json`) and adversarial (`eval/datasets/adversarial.json`) data:

1. **Accuracy:** Overall percentage of correct triage decisions.
2. **Precision per Category:** Class-specific routing correctness.
3. **Escalation Rate:** Ratio of correct escalations vs. unnecessary escalations.
4. **Adversarial-Pass Rate:** Resistance to prompt injection and hidden legal exposures.
5. **False-Confidence Rate:** Percentage of decisions where the agent is confidently wrong (confidence ≥ 0.75 but incorrect).
