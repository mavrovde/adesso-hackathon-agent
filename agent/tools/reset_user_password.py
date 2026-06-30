"""Tool: reset_user_password

Executes a password reset for the given user on the given system.
Returns the credential delivery method (e.g. "email", "SMS").

Does NOT:
  - reset passwords for FROZEN or UNDER_INVESTIGATION accounts (hard-blocked by PreToolUse hook)
  - reset passwords without a valid user_id and system
  - expose the new temporary password in the response

Input:  user_id (str), system (str) — e.g. "active_directory", "vpn", "email"
Output: { ok: true, data: { user_id, system, delivery_method } }
        { ok: false, isError: true, code: "ACCOUNT_FROZEN" | "USER_NOT_FOUND" | "UNSUPPORTED_SYSTEM", guidance: "..." }
"""
from __future__ import annotations
from agent.tools.mock_store import USERS

SUPPORTED_SYSTEMS = {"active_directory", "vpn", "email", "slack"}
BLOCKED_STATUSES = {"FROZEN", "UNDER_INVESTIGATION"}


def reset_user_password(user_id: str, system: str) -> dict:
    user = USERS.get(user_id)
    if not user:
        return {
            "ok": False,
            "isError": True,
            "code": "USER_NOT_FOUND",
            "guidance": f"No user with id '{user_id}'. Verify the user_id.",
        }

    if user["account_status"] in BLOCKED_STATUSES:
        return {
            "ok": False,
            "isError": True,
            "code": "ACCOUNT_FROZEN",
            "guidance": f"Account '{user_id}' is {user['account_status']}. Escalate to security team.",
        }

    if system not in SUPPORTED_SYSTEMS:
        return {
            "ok": False,
            "isError": True,
            "code": "UNSUPPORTED_SYSTEM",
            "guidance": f"System '{system}' is not supported. Supported: {sorted(SUPPORTED_SYSTEMS)}.",
        }

    delivery_method = "email" if user.get("vip") else "email"
    return {"ok": True, "data": {"user_id": user_id, "system": system, "delivery_method": delivery_method}}
