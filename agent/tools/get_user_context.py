"""Tool: get_user_context

Returns the user's role, department, account status, and recent tickets.
Does NOT return passwords, raw credentials, or audit logs.

Input:  user_id (str)
Output: { ok: true, data: { user_id, name, role, department, account_status, vip, recent_tickets } }
        { ok: false, isError: true, code: "USER_NOT_FOUND", guidance: "..." }
"""
from __future__ import annotations
from agent.tools.mock_store import USERS


def get_user_context(user_id: str) -> dict:
    user = USERS.get(user_id)
    if not user:
        return {
            "ok": False,
            "isError": True,
            "code": "USER_NOT_FOUND",
            "guidance": f"No user with id '{user_id}' exists. Verify the user_id and retry.",
        }
    return {"ok": True, "data": user}
