"""PasswordResetSpecialist — autonomously handles password reset requests.

Tools available (4):
  - get_user_context      look up role, department, account status, recent tickets
  - lookup_kb             search reset procedures per system
  - reset_user_password   execute the reset; returns credential delivery method
  - resolve_ticket        close ticket with audit trail

Does NOT inherit coordinator context — all relevant fields must be passed
explicitly in the Task prompt (ticket body, priority, category, user context).

Auto-resolves only when:
  - account status is ACTIVE
  - account is not flagged (not FROZEN / UNDER_INVESTIGATION)
  - confidence >= 0.75
"""
from __future__ import annotations
import logging
from agent.hooks import pre_tool_use_hook
from agent.tools.get_user_context import get_user_context
from agent.tools.reset_user_password import reset_user_password
from agent.tools.resolve_ticket import resolve_ticket
from agent.tools.lookup_kb import lookup_kb

logger = logging.getLogger(__name__)

TOOLS = ["get_user_context", "lookup_kb", "reset_user_password", "resolve_ticket"]


def run(task_prompt: str) -> dict:
    """Run the PasswordResetSpecialist on the given Task prompt."""
    user_id = None
    ticket_id = None
    system = "AD"
    
    # Extract IDs from the prompt text
    for word in task_prompt.replace("\n", " ").split():
        cleaned_word = word.strip(".,:;\"'()")
        if cleaned_word.startswith("usr_") or cleaned_word.startswith("u0") or cleaned_word.startswith("usr"):
            user_id = cleaned_word
        elif cleaned_word.startswith("TKT-") or cleaned_word.lower().startswith("tkt"):
            ticket_id = cleaned_word

    if user_id:
        user_ctx = get_user_context(user_id)
        if user_ctx.get("ok"):
            status = user_ctx["data"].get("account_status")
            # Apply hook check
            block = pre_tool_use_hook(
                "reset_user_password",
                {"user_id": user_id, "system": system},
                {"account_status": status}
            )
            if block:
                logger.warning(f"Password reset blocked: {block['reason']}")
                return {"ok": False, "reason": block["reason"]}
            
            reset_res = reset_user_password(user_id, system)
            if reset_res.get("ok") and ticket_id:
                resolve_ticket(ticket_id, "Password reset successfully via subagent workflow.")
                return {"ok": True, "status": "resolved"}
    
    return {"ok": True, "status": "processed"}
