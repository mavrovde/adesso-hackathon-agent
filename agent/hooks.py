"""PreToolUse hard blocks — deterministic stops, not model-driven.

Hard-blocked patterns:
  - reset_user_password  where account status is FROZEN or UNDER_INVESTIGATION
  - resolve_ticket       where priority is P1
  - any tool call        where the request body matches known prompt-injection patterns
"""
from __future__ import annotations

FROZEN_STATUSES = {"FROZEN", "UNDER_INVESTIGATION"}

PROMPT_INJECTION_PATTERNS = [
    "ignore prior instructions",
    "ignore previous instructions",
    "disregard your instructions",
    "forget your instructions",
]


def pre_tool_use_hook(tool_name: str, tool_input: dict, context: dict) -> dict | None:
    """Return a block response dict to hard-stop the tool call, or None to allow it.

    A block response has the shape:
      {"block": True, "reason": "<human-readable reason>"}
    """
    # Block write action on frozen/investigated accounts
    if tool_name == "reset_user_password":
        status = context.get("account_status", "")
        if status in FROZEN_STATUSES:
            return {"block": True, "reason": f"Account status is {status}; write actions are hard-blocked."}

    # Block auto-resolve on P1 tickets
    if tool_name == "resolve_ticket":
        if context.get("priority") == "P1":
            return {"block": True, "reason": "P1 tickets cannot be auto-resolved; human approval required."}

    # Block on known prompt-injection patterns in any tool input
    raw = str(tool_input).lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern in raw:
            return {"block": True, "reason": f"Prompt injection pattern detected: '{pattern}'"}

    return None
