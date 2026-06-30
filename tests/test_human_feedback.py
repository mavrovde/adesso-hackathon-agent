from __future__ import annotations
import json
import pytest

from agent.tools.mock_store import reset_store, TICKETS
from agent.tools.create_or_update_ticket import create_or_update_ticket
from agent.human_feedback import override_agent_decision, get_few_shot_examples, OVERRIDES_FILE


@pytest.fixture(autouse=True)
def clean_store_and_dataset():
    reset_store()
    if OVERRIDES_FILE.exists():
        try:
            OVERRIDES_FILE.unlink()
        except OSError:
            pass
    yield
    if OVERRIDES_FILE.exists():
        try:
            OVERRIDES_FILE.unlink()
        except OSError:
            pass


def test_override_agent_decision_success():
    # 1. Create a ticket
    original_text = "I forgot my AD password."
    res = create_or_update_ticket(
        ticket_id=None,
        priority="P4",
        queue="password_reset",
        category="password_reset",
        summary="Forgot AD password",
        requester_id="u001",
        original_input=original_text,
    )
    assert res["ok"] is True
    ticket_id = res["data"]["ticket_id"]

    # 2. Perform human override
    override_res = override_agent_decision(
        ticket_id=ticket_id,
        human_category="access",
        human_priority="P2",
        human_escalated=True,
        overrider_id="admin_01",
        reason="User actually needs admin rights to AD, not just reset.",
    )

    assert override_res["ok"] is True
    assert override_res["data"]["recorded"] is True

    # Verify ticket state in mock store
    ticket = TICKETS[ticket_id]
    assert ticket["category"] == "access"
    assert ticket["priority"] == "P2"
    assert ticket["status"] == "ESCALATED"
    assert ticket["override_log"]["overrider_id"] == "admin_01"
    assert ticket["override_log"]["reason"] == "User actually needs admin rights to AD, not just reset."

    # Verify file content
    assert OVERRIDES_FILE.exists()
    with open(OVERRIDES_FILE) as f:
        cases = json.load(f)
    assert len(cases) == 1
    assert cases[0]["input"] == original_text
    assert cases[0]["expected"]["category"] == "access"
    assert cases[0]["expected"]["priority"] == "P2"
    assert cases[0]["expected"]["escalated"] is True

    # Verify few shot examples
    examples = get_few_shot_examples(limit=1)
    assert len(examples) == 1
    assert examples[0]["input"] == original_text
    assert examples[0]["category"] == "access"
    assert examples[0]["priority"] == "P2"


def test_override_agent_decision_invalid_inputs():
    res = create_or_update_ticket(
        ticket_id=None,
        priority="P4",
        queue="password_reset",
        category="password_reset",
        summary="Forgot AD password",
        requester_id="u001",
    )
    ticket_id = res["data"]["ticket_id"]

    # Test missing overrider
    err = override_agent_decision(
        ticket_id=ticket_id,
        human_category="access",
        human_priority="P2",
        human_escalated=True,
        overrider_id="",
        reason="Some reason",
    )
    assert err["ok"] is False
    assert err["code"] == "MISSING_OVERRIDER_ID"

    # Test missing reason
    err = override_agent_decision(
        ticket_id=ticket_id,
        human_category="access",
        human_priority="P2",
        human_escalated=True,
        overrider_id="admin_01",
        reason="   ",
    )
    assert err["ok"] is False
    assert err["code"] == "MISSING_REASON"
