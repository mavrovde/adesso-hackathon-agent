"""Tool: resolve_ticket

Closes a ticket with a resolution summary and audit trail.

Does NOT:
  - resolve P1 tickets (hard-blocked by PreToolUse hook)
  - resolve tickets that have already been closed

Input:  ticket_id (str), resolution_summary (str)
Output: { ok: true, data: { ticket_id, status: "RESOLVED", resolution_summary } }
        { ok: false, isError: true, code: "TICKET_NOT_FOUND" | "ALREADY_RESOLVED" | "P1_BLOCKED", guidance: "..." }
"""
from __future__ import annotations
from agent.tools.mock_store import TICKETS


def resolve_ticket(ticket_id: str, resolution_summary: str) -> dict:
    ticket = TICKETS.get(ticket_id)
    if not ticket:
        return {
            "ok": False,
            "isError": True,
            "code": "TICKET_NOT_FOUND",
            "guidance": f"Ticket '{ticket_id}' not found. Verify the ticket_id.",
        }

    if ticket.get("status") == "RESOLVED":
        return {
            "ok": False,
            "isError": True,
            "code": "ALREADY_RESOLVED",
            "guidance": f"Ticket '{ticket_id}' is already resolved.",
        }

    if ticket.get("priority") == "P1":
        return {
            "ok": False,
            "isError": True,
            "code": "P1_BLOCKED",
            "guidance": "P1 tickets cannot be auto-resolved. Escalate for human approval.",
        }

    ticket["status"] = "RESOLVED"
    ticket["resolution_summary"] = resolution_summary
    return {"ok": True, "data": {"ticket_id": ticket_id, "status": "RESOLVED", "resolution_summary": resolution_summary}}
