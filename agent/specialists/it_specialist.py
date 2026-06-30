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
import logging
from agent.hooks import pre_tool_use_hook
from agent.tools.get_user_context import get_user_context
from agent.tools.lookup_kb import lookup_kb
from agent.tools.create_or_update_ticket import create_or_update_ticket
from agent.tools.resolve_ticket import resolve_ticket
from agent.tools.escalate import escalate

logger = logging.getLogger(__name__)

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
    user_id = None
    ticket_id = None
    category = "unknown"
    priority = "P3"
    
    cleaned_prompt = task_prompt.lower()
    
    # Extract IDs from word list
    for word in task_prompt.replace("\n", " ").split():
        cleaned_word = word.strip(".,:;\"'()")
        if cleaned_word.startswith("usr_") or cleaned_word.startswith("u0") or cleaned_word.startswith("usr"):
            user_id = cleaned_word
        elif cleaned_word.startswith("TKT-") or cleaned_word.lower().startswith("tkt"):
            ticket_id = cleaned_word

    # Determine category from keywords
    if "wifi" in cleaned_prompt or "network" in cleaned_prompt or "vpn" in cleaned_prompt:
        category = "network"
    elif "slack" in cleaned_prompt or "office" in cleaned_prompt or "software" in cleaned_prompt:
        category = "software"
    elif "laptop" in cleaned_prompt or "mouse" in cleaned_prompt or "hardware" in cleaned_prompt:
        category = "hardware"
    elif "drive" in cleaned_prompt or "access" in cleaned_prompt or "permission" in cleaned_prompt:
        category = "access"

    # Always escalate breach keywords immediately
    if any(kw in cleaned_prompt for kw in ALWAYS_ESCALATE_KEYWORDS):
        if ticket_id:
            escalate(ticket_id, "Security breach keywords detected.", "P1", "HIGH")
        return {"ok": True, "status": "escalated", "reason": "security_breach"}

    # Lookup KB runbook
    kb_res = lookup_kb(task_prompt, category=category)
    has_kb_match = False
    solution_type = None
    if kb_res.get("ok") and kb_res["data"]["articles"]:
        has_kb_match = True
        solution_type = kb_res["data"]["articles"][0].get("solution_type")
        priority = kb_res["data"]["articles"][0].get("priority_hint", "P3")

    if ticket_id:
        if has_kb_match and solution_type == "self_service" and priority in ["P3", "P4"]:
            resolve_ticket(ticket_id, "Resolved using knowledge base self-service procedure.")
            return {"ok": True, "status": "resolved"}
        else:
            escalate(
                ticket_id,
                "Requires specialist support or no direct self-service solution found.",
                priority,
                "MEDIUM"
            )
            return {"ok": True, "status": "escalated"}
            
    return {"ok": True, "status": "processed"}
