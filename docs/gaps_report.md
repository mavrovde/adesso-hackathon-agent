# Gap Analysis Report — IT Helpdesk Triage Agent

This document outlines the gaps between the requirements (defined in `TASK.md`, `MANDATE.md`, `PLAN.md`) and the current state of the codebase.

---

## 1. Scorecard Metrics Gaps (`eval/run.py`)

* **Requirement:** The scorecard must report:
  - Accuracy (overall correct decisions)
  - Precision per category (breakdown of classification)
  - Escalation rate (correct vs. needless escalations)
  - Adversarial-pass rate (injection and legal-exposure resistance)
  - False-confidence rate (how often the agent is confidently wrong)
* **Current State:** `eval/run.py` only computes overall accuracy and passes/fails. It does **not** calculate precision per category, escalation rates, adversarial-pass rate, or false-confidence rate.
* **Impact:** High. Legal and stakeholder review requires a defensible scorecard with these specific metrics.

---

## 2. Coordinator Agent Gaps (`agent/coordinator.py`)

* **Requirement:** Ingest a request, classify it, enrich with context, log reasoning chain, and wrap in a validation-retry loop (up to N times) sending Pydantic validation errors back to Claude.
* **Current State:** The file `agent/coordinator.py` only contains imports and constants. `run_coordinator` raises `NotImplementedError`.
* **Impact:** Blocker. The entry point (`agent/main.py`) and the evaluation harness (`eval/run.py`) both crash because the coordinator has no implementation.

---

## 3. Specialist Subagents Gaps (`agent/specialists/`)

* **Requirement:**
  - `PasswordResetSpecialist` must autonomously handle password resets using its 4 tools.
  - `ITSpecialistAgent` must handle other categories using its 5 tools.
  - Both must run in separate, isolated context sessions using the Claude Agent SDK `Task` API and handle `stop_reason` (e.g. `tool_use`, `max_tokens`, `end_turn`).
* **Current State:** Both `password_reset.py` and `it_specialist.py` contain only imports and tool list declarations. The `run` functions raise `NotImplementedError`.
* **Impact:** Blocker. Subagents cannot process the routed tickets.

---

## 4. Hook Integration Gaps (`agent/hooks.py`)

* **Requirement:** Integrate a `PreToolUse` hook that deterministically blocks write actions on frozen accounts, P1 ticket auto-resolutions, and prompt injection patterns.
* **Current State:** The logic is written in `hooks.py`, but it is **not connected** to any active agent loop since neither the coordinator nor the specialists are implemented.
* **Impact:** Blocker. Security and safety policies are not enforced during run-time.

---

## 5. Mock Ticketing State Persistence (`agent/tools/mock_store.py`)

* **Requirement:** The evaluation harness runs in sequence, resetting the store between cases.
* **Current State:** `reset_store()` is implemented in `mock_store.py` and called in `eval/run.py`. However, `TICKETS` dict is cleared but `USERS` dictionary status (e.g. frozen/vip) is static. Ensure we reset user status if tests change it.
