# adesso-hackathon-agent

An agentic intake and triage solution built on the [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) for the Adesso hackathon (Scenario 5 — "The Intake").

Inbound requests arrive across multiple channels, get classified, enriched with context, and routed to the right internal team — without a human in the middle for the routine cases, and with a hard human-in-the-loop brake for anything risky.

---

## What the Agent Decides

| Decision | Agent acts alone | Agent escalates |
|---|---|---|
| Classify incoming request | Always | — |
| Route to internal team/queue | High-confidence cases | Low confidence or ambiguous |
| Auto-resolve trivial requests | Known patterns (e.g. password resets) | — |
| Write to system of record | Standard cases | High-risk patterns, PII exposure, frozen accounts |
| Flag adversarial / injection attempts | Hard block via `PreToolUse` hook | — |

What the agent deliberately does **not** automate: final denial of high-stakes requests, any action on legally sensitive accounts, and override of a human decision.

---

## Architecture

```
Inbound request
      │
      ▼
┌─────────────────┐
│  Coordinator    │  classifies · enriches · routes
│  Agent          │  validates structured output (retry loop)
└────────┬────────┘
         │ Task prompt (explicit context — subagents do NOT inherit coordinator context)
    ┌────┴────┐
    ▼         ▼
Specialist  Specialist   ...
Agent A     Agent B
(routing)   (resolution)
    │
    ▼
PreToolUse hook — hard block on high-risk write patterns
    │
    ▼
System of record / downstream action
```

**Coordinator** handles classification, enrichment, and routing. It wraps structured output in a validation-retry loop (up to N retries; error type and retry count are logged per request).

**Specialist subagents** each have a focused tool set (~4–5 tools). Context is passed explicitly in each Task prompt; specialists are stateless with respect to each other.

**Permission hooks** (`PreToolUse`) deterministically block the write tool on known high-risk patterns before Claude ever decides. The escalation rules (category + confidence threshold + impact bucket) are a slow stop; the hook is a hard stop.

---

## Tech Stack

- **Runtime:** Python (Claude Agent SDK)
- **LLM:** Claude via `ANTHROPIC_API_KEY`
- **Agent SDK docs:**
  - [Overview](https://docs.claude.com/en/api/agent-sdk/overview)
  - [Python reference](https://docs.claude.com/en/api/agent-sdk/python)
  - [Custom tools](https://docs.claude.com/en/api/agent-sdk/custom-tools)
  - [Permissions and approvals](https://docs.claude.com/en/api/agent-sdk/permissions)

---

## Setup

```bash
# Clone and enter the repo
git clone https://github.com/mavrovde/adesso-hackathon-agent.git
cd adesso-hackathon-agent

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here
```

---

## Running the Agent & Evals

To ensure dependencies (like `pydantic` and `anthropic`) are correctly loaded, run commands using the virtual environment's python interpreter:

```bash
# Run the coordinator with a sample request
PYTHONPATH=. .venv/bin/python3 -m agent.main --input "My laptop won't connect to WiFi since this morning."

# Run against the full eval harness (all suites)
PYTHONPATH=. .venv/bin/python3 -m eval.run

# Run only the adversarial eval set
PYTHONPATH=. .venv/bin/python3 -m eval.run --suite adversarial

# Run only the overrides eval set (capturing human corrections)
PYTHONPATH=. .venv/bin/python3 -m eval.run --suite overrides
```

---

## Project Structure

```
agent/
  main.py            # entry point, coordinator agent loop
  coordinator.py     # classification, enrichment, routing logic
  human_feedback.py  # Human overrides feedback collector and few-shot loader
  specialists/       # one module per specialist subagent (stateless)
  tools/             # custom tool definitions (mock database & KB lookup)
  hooks.py           # PreToolUse permission hooks (deterministic guardrails)
eval/
  run.py             # eval harness (scorecard)
  datasets/          # labeled request sets (normal, adversarial, overrides)
demo.html            # Interactive Live Demo UI (employee portal + operator queue)
presentation.html    # Glassmorphic pitch presentation slides
```

---

## Interactive UI & Slides

- **Live Demo UI (`demo.html`):** Open this file directly in any browser. It provides an employee portal with pre-loaded scenarios to watch the agent classify and route, and an IT operator queue showing confidence bars, coordinator reasoning chains, and manual Approve / Override actions.
- **Pitch Slides (`presentation.html`):** Open this file in your browser to view the self-contained 12-slide glassmorphic presentation covering our architecture, deterministic guardrails, evaluation scorecard, and live walk-throughs.

---

## Human Feedback Loop (Stretch Goal ✓)

We closed the agent learning loop with a human-in-the-loop override mechanism:
1. **Override Capture (`agent/human_feedback.py`):** When an operator overrides a ticket route, the overrider ID and justification are recorded onto the ticket audit log and saved to `eval/datasets/overrides.json`.
2. **In-Context Few-Shot Learning:** The coordinator dynamically reads the latest overrides and injects them back into its prompt as custom few-shot exemplars, teaching the agent correct routing without model retraining.
3. **Regression Prevention:** The overrides suite is run as part of the scorecard eval check to ensure the agent doesn't regress on human-corrected scenarios.

---

## Eval Metrics

The eval harness (`eval/run.py`) reports:

- **Accuracy** — overall correct decisions
- **Precision per category** — breakdown by request type
- **Escalation rate** — correct escalations vs. needless escalations
- **Adversarial-pass rate** — prompt injection and edge-case resistance
- **False-confidence rate** — how often the agent is confidently wrong

Runs in CI so the score moves as the agent changes and produces a defensible artifact for stakeholder review.

---

## Security Notes

- `PreToolUse` hooks provide a hard, deterministic block on write actions matching high-risk patterns (PII exfiltration, actions on frozen accounts, known-bad routes). This is not model-driven — it fires before Claude decides.
- The adversarial eval set covers prompt injection in the request body, ambiguous urgency signals, and requests with hidden legal exposure.
- Escalation rules are explicit (category + confidence threshold + dollar-impact bucket) to produce consistent, auditable behavior.

---

## License

MIT

