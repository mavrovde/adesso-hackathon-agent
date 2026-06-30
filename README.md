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

## Running the Agent

```bash
# Run the coordinator with a sample request
python -m agent.main --input "Sample inbound request text"

# Run against the full eval harness
python -m eval.run

# Run only the adversarial eval set
python -m eval.run --suite adversarial
```

---

## Project Structure

```
agent/
  main.py          # entry point, coordinator agent loop
  coordinator.py   # classification, enrichment, routing logic
  specialists/     # one module per specialist subagent
  tools/           # custom tool definitions
  hooks.py         # PreToolUse permission hooks
eval/
  run.py           # eval harness
  datasets/        # labeled request sets (normal + adversarial)
```

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
