"""ITSpecialistAgent — handles all non-password-reset incident categories.

Categories: network · software · hardware · access · vip_escalation · unknown

Tools available (5):
  - get_user_context          look up role, department, account status, recent tickets
  - lookup_kb                 search for known issues and runbooks
  - create_or_update_ticket   write ticket with priority, queue, classification
  - resolve_ticket            auto-close on unambiguous KB match (P3/P4 only)
  - escalate                  trigger human-in-the-loop with full context

Does NOT inherit coordinator context — all relevant fields must be passed
explicitly in the Task prompt (ticket body, priority, category, user context).

Auto-resolves only P3/P4 tickets with an unambiguous KB match.
Always escalates: P1, P2 write actions, VIP, legal/compliance mentions,
confidence < 0.75, or security breach keywords.
"""
from __future__ import annotations

# TODO: implement with Claude Agent SDK Task subagent

TOOLS = [
    "get_user_context",
    "lookup_kb",
    "create_or_update_ticket",
    "resolve_ticket",
    "escalate",
]

ALWAYS_ESCALATE_KEYWORDS = ["breach", "ransomware", "exfil", "data leak", "compromise"]


def run(task_prompt: str) -> dict:
    """Run the ITSpecialistAgent on the given Task prompt."""
    raise NotImplementedError
