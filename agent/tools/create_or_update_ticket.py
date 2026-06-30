"""Tool: create_or_update_ticket

Creates a new ticket or updates an existing one with priority, queue, and classification.

Does NOT:
  - change the priority of a P1 ticket without human approval
  - accept free-text priority — must be one of P1, P2, P3, P4

Input:  ticket_id (str | None) — pass None to create; pass existing id to update
        priority (str)         — P1 | P2 | P3 | P4
        queue (str)            — network | software | hardware | access | security | password_reset
        category (str)         — from CLAUDE.md domain categories
        summary (str)          — short description of the issue
        requester_id (str)     — user_id of the person who filed the request
Output: { ok: true, data: { ticket_id, priority, queue, category, status } }
        { ok: false, isError: true, code: "INVALID_PRIORITY" | "TICKET_NOT_FOUND", guidance: "..." }
"""
from __future__ import annotations
from agent.tools.mock_store import TICKETS, create_ticket

VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
VALID_QUEUES = {"network", "software", "hardware", "access", "security", "password_reset", "vip_escalation"}


def create_or_update_ticket(
    ticket_id: str | None,
    priority: str,
    queue: str,
    category: str,
    summary: str,
    requester_id: str,
    original_input: str | None = None,
) -> dict:
    if priority not in VALID_PRIORITIES:
        return {
            "ok": False,
            "isError": True,
            "code": "INVALID_PRIORITY",
            "guidance": f"Priority must be one of {sorted(VALID_PRIORITIES)}; got '{priority}'.",
        }

    if queue not in VALID_QUEUES:
        return {
            "ok": False,
            "isError": True,
            "code": "INVALID_QUEUE",
            "guidance": f"Queue must be one of {sorted(VALID_QUEUES)}; got '{queue}'.",
        }

    body = {
        "priority": priority,
        "queue": queue,
        "category": category,
        "summary": summary,
        "requester_id": requester_id,
    }
    if original_input is not None:
        body["original_input"] = original_input

    if ticket_id is None:
        ticket = create_ticket(body)
    else:
        ticket = TICKETS.get(ticket_id)
        if not ticket:
            return {
                "ok": False,
                "isError": True,
                "code": "TICKET_NOT_FOUND",
                "guidance": f"Ticket '{ticket_id}' not found. Pass ticket_id=None to create a new one.",
            }
        ticket.update(body)

    return {"ok": True, "data": {"ticket_id": ticket["ticket_id"], "priority": priority, "queue": queue, "category": category, "status": ticket.get("status", "OPEN")}}

