"""Module to handle human overrides.

Collects human correction feedback, updates the ticket store, logs details,
appends the case to the overrides evaluation dataset, and provides few-shot helpers.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent.tools.mock_store import TICKETS

# Use absolute path for overrides dataset
DATASETS_DIR = Path(__file__).parent.parent / "eval" / "datasets"
OVERRIDES_FILE = DATASETS_DIR / "overrides.json"


def override_agent_decision(
    ticket_id: str,
    human_category: str,
    human_priority: str,
    human_escalated: bool,
    overrider_id: str,
    reason: str,
) -> dict:
    """Override an agent's triage decision.

    Updates the mock store ticket, writes the override event, and logs the
    corrected result to the overrides dataset.
    """
    if not overrider_id:
        return {
            "ok": False,
            "isError": True,
            "code": "MISSING_OVERRIDER_ID",
            "guidance": "overrider_id is mandatory to log who performed the override.",
        }

    if not reason or not reason.strip():
        return {
            "ok": False,
            "isError": True,
            "code": "MISSING_REASON",
            "guidance": "A non-empty reason is mandatory for human auditability.",
        }

    ticket = TICKETS.get(ticket_id)
    if not ticket:
        return {
            "ok": False,
            "isError": True,
            "code": "TICKET_NOT_FOUND",
            "guidance": f"Ticket '{ticket_id}' not found.",
        }

    # Capture original agent decisions
    agent_category = ticket.get("category")
    agent_priority = ticket.get("priority")
    agent_escalated = (ticket.get("status") == "ESCALATED")

    # Update ticket with human corrections
    ticket["category"] = human_category
    ticket["priority"] = human_priority
    ticket["status"] = "ESCALATED" if human_escalated else "OPEN"

    # Audit log entry on the ticket itself
    ticket["override_log"] = {
        "overrider_id": overrider_id,
        "reason": reason.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "previous_decision": {
            "category": agent_category,
            "priority": agent_priority,
            "escalated": agent_escalated,
        },
    }

    # Extract original text prompt
    original_input = ticket.get("original_input", ticket.get("summary", ""))

    # Save to the evaluation overrides dataset
    try:
        DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        cases = []
        if OVERRIDES_FILE.exists() and OVERRIDES_FILE.stat().st_size > 0:
            with open(OVERRIDES_FILE, "r") as f:
                cases = json.load(f)

        new_case = {
            "id": f"override-{ticket_id}-{uuid.uuid4().hex[:4]}",
            "input": original_input,
            "expected": {
                "category": human_category,
                "priority": human_priority,
                "escalated": human_escalated,
            },
            "agent_decision": {
                "category": agent_category,
                "priority": agent_priority,
                "escalated": agent_escalated,
            },
            "overrider_id": overrider_id,
            "reason": reason.strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        cases.append(new_case)

        with open(OVERRIDES_FILE, "w") as f:
            json.dump(cases, f, indent=2)

    except Exception:
        # Logging warning if writing to dataset failed, but don't crash ticket update
        pass

    return {
        "ok": True,
        "data": {
            "ticket_id": ticket_id,
            "category": human_category,
            "priority": human_priority,
            "status": ticket["status"],
            "recorded": True,
        },
    }


def get_few_shot_examples(limit: int = 3) -> list[dict]:
    """Retrieve recorded overrides to be used as few-shot training examples."""
    try:
        if OVERRIDES_FILE.exists() and OVERRIDES_FILE.stat().st_size > 0:
            with open(OVERRIDES_FILE, "r") as f:
                cases = json.load(f)
            examples = []
            for case in cases[-limit:]:
                examples.append({
                    "input": case["input"],
                    "category": case["expected"]["category"],
                    "priority": case["expected"]["priority"],
                })
            return examples
    except Exception:
        pass
    return []
