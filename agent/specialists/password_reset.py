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

# TODO: implement with Claude Agent SDK Task subagent

TOOLS = ["get_user_context", "lookup_kb", "reset_user_password", "resolve_ticket"]


def run(task_prompt: str) -> dict:
    """Run the PasswordResetSpecialist on the given Task prompt."""
    raise NotImplementedError
