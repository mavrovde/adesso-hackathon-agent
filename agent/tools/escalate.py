"""Tool: escalate

Triggers human-in-the-loop by flagging a ticket for human review.
Logs the full escalation context so the approver has everything they need.

Does NOT:
  - take any write action on the ticket itself
  - notify the requester — that is the approver's responsibility

Input:  ticket_id (str)
        reason (str)     — plain-language escalation reason
        severity (str)   — "low" | "medium" | "high" | "critical"
        impact (str)     — short description of business impact
Output: { ok: true, data: { ticket_id, escalated: true, severity, reason } }
        { ok: false, isError: true, code: "TICKET_NOT_FOUND" | "INVALID_SEVERITY", guidance: "..." }
"""
from __future__ import annotations
from agent.tools.mock_store import TICKETS

VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def escalate(ticket_id: str, reason: str, severity: str, impact: str) -> dict:
    if severity not in VALID_SEVERITIES:
        return {
            "ok": False,
            "isError": True,
            "code": "INVALID_SEVERITY",
            "guidance": f"Severity must be one of {sorted(VALID_SEVERITIES)}; got '{severity}'.",
        }

    ticket = TICKETS.get(ticket_id)
    if not ticket:
        return {
            "ok": False,
            "isError": True,
            "code": "TICKET_NOT_FOUND",
            "guidance": f"Ticket '{ticket_id}' not found. Create the ticket first with create_or_update_ticket.",
        }

    ticket["status"] = "ESCALATED"
    ticket["escalation"] = {"reason": reason, "severity": severity, "impact": impact}

    return {
        "ok": True,
        "data": {
            "ticket_id": ticket_id,
            "escalated": True,
            "severity": severity,
            "reason": reason,
        },
    }
