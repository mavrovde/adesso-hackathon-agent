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

import json
import logging
import re
from typing import Any

import anthropic

from agent.hooks import pre_tool_use_hook
from agent.tools.get_user_context import get_user_context
from agent.tools.lookup_kb import lookup_kb
from agent.tools.reset_user_password import reset_user_password
from agent.tools.resolve_ticket import resolve_ticket

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 15

SYSTEM_PROMPT = """You are the PasswordResetSpecialist. You handle password reset requests for active, non-flagged accounts.

## Required execution flow — follow this exactly:
1. Call get_user_context(user_id) to check account status.
2. Call lookup_kb(query, category="password_reset") to find the correct reset procedure.
3. If account_status is ACTIVE (not FROZEN, not UNDER_INVESTIGATION):
   → Call reset_user_password(user_id, system) — you MUST call this tool. Do not skip it.
   → Then call resolve_ticket(ticket_id, resolution_summary) to close the ticket.
4. If account_status is FROZEN or UNDER_INVESTIGATION:
   → Do NOT call reset_user_password. Stop and report that escalation is required.

IMPORTANT: When the account is eligible (ACTIVE, not flagged), calling reset_user_password is mandatory.
Do not ask for confirmation, do not defer to a human, do not skip the reset.
Use system="active_directory" for AD/password requests unless the task prompt specifies otherwise."""

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_user_context",
        "description": (
            "Look up a user's role, department, account_status (ACTIVE/FROZEN/UNDER_INVESTIGATION), "
            "vip flag, and recent tickets. Call this FIRST before any write action to verify the "
            "account is eligible for a password reset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The unique user identifier (e.g. 'u001').",
                }
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "lookup_kb",
        "description": (
            "Search the knowledge base for password reset procedures and runbooks. "
            "Call this before executing a reset to identify the correct procedure for the target system."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language or keyword search query.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category to narrow results (e.g. 'password_reset').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "reset_user_password",
        "description": (
            "Execute a password reset for the given user on the given system. "
            "Only call this after confirming via get_user_context that the account is ACTIVE and not flagged. "
            "Returns the credential delivery method. Hard-blocked for FROZEN/UNDER_INVESTIGATION accounts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The unique user identifier.",
                },
                "system": {
                    "type": "string",
                    "description": (
                        "The system to reset the password on. "
                        "Supported: 'active_directory', 'vpn', 'email', 'slack'."
                    ),
                },
            },
            "required": ["user_id", "system"],
        },
    },
    {
        "name": "resolve_ticket",
        "description": (
            "Close a ticket with a resolution summary for the audit trail. "
            "Call this after a successful password reset. Hard-blocked for P1 tickets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "The ticket identifier to resolve.",
                },
                "resolution_summary": {
                    "type": "string",
                    "description": "Human-readable summary of the resolution for the audit trail.",
                },
            },
            "required": ["ticket_id", "resolution_summary"],
        },
    },
]

_TOOL_DISPATCH = {
    "get_user_context": lambda inp: get_user_context(inp["user_id"]),
    "lookup_kb": lambda inp: lookup_kb(inp["query"], inp.get("category")),
    "reset_user_password": lambda inp: reset_user_password(inp["user_id"], inp["system"]),
    "resolve_ticket": lambda inp: resolve_ticket(inp["ticket_id"], inp["resolution_summary"]),
}


def _extract_priority(task_prompt: str) -> str:
    """Extract priority (P1–P4) from the task prompt, default to P3."""
    match = re.search(r"\bP[1-4]\b", task_prompt)
    return match.group(0) if match else "P3"


def _extract_ticket_id(task_prompt: str) -> str | None:
    """Extract a ticket ID (e.g. TKT-XXXXXX) from the task prompt."""
    match = re.search(r"\bTKT-[A-Z0-9]+\b", task_prompt)
    return match.group(0) if match else None


def _get_text_from_message(message: anthropic.types.Message) -> str:
    """Extract concatenated text from all text blocks in a message."""
    parts: list[str] = []
    for block in message.content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def run(task_prompt: str) -> dict:
    """Run the PasswordResetSpecialist on the given Task prompt.

    Args:
        task_prompt: Full task context including original request, category,
                     priority, user_id, ticket_id, and any KB snippets.

    Returns:
        {
            "action_taken": "auto_resolved" | "escalated" | "failed",
            "escalated": bool,
            "ticket_id": str | None,
            "resolution_summary": str,
            "routing_target": str,
            "reasoning": str,
        }
    """
    client = anthropic.Anthropic()

    priority = _extract_priority(task_prompt)
    ticket_id = _extract_ticket_id(task_prompt)

    # Hook context — updated as we discover account status
    hook_context: dict[str, str] = {"priority": priority}

    messages: list[dict[str, Any]] = [{"role": "user", "content": task_prompt}]

    # State tracking
    reset_executed = False
    reset_blocked = False
    ticket_resolved = False
    escalated = False
    final_text = ""

    for iteration in range(MAX_ITERATIONS):
        logger.debug("PasswordResetSpecialist iteration %d", iteration)

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,  # type: ignore[arg-type]
            messages=messages,
        )

        if response.stop_reason == "max_tokens":
            logger.warning(
                "PasswordResetSpecialist hit max_tokens at iteration %d",
                iteration,
            )
            break

        if response.stop_reason == "end_turn":
            final_text = _get_text_from_message(response)
            break

        if response.stop_reason == "tool_use":
            # Append the assistant's message (may contain text + tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            tool_results: list[dict[str, Any]] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name: str = block.name
                tool_input: dict[str, Any] = block.id and block.input or {}  # type: ignore[assignment]
                # block.input is always a dict for tool_use blocks
                tool_input = block.input  # type: ignore[assignment]

                # Update hook context with discovered account status
                if tool_name == "get_user_context":
                    # We'll update after we get the result; pass what we have
                    pass

                # --- Pre-tool-use hook ---
                block_result = pre_tool_use_hook(tool_name, tool_input, hook_context)
                if block_result and block_result.get("block"):
                    reason: str = block_result.get("reason", "Blocked by pre_tool_use_hook")
                    logger.info(
                        "pre_tool_use_hook blocked tool=%s reason=%s",
                        tool_name,
                        reason,
                    )
                    if tool_name == "reset_user_password":
                        reset_blocked = True
                        escalated = True
                    tool_result_content = json.dumps({
                        "ok": False,
                        "isError": True,
                        "code": "HOOK_BLOCKED",
                        "guidance": reason,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result_content,
                    })
                    continue

                # --- Execute the tool ---
                dispatcher = _TOOL_DISPATCH.get(tool_name)
                if dispatcher is None:
                    tool_result_content = json.dumps({
                        "ok": False,
                        "isError": True,
                        "code": "UNKNOWN_TOOL",
                        "guidance": f"Tool '{tool_name}' is not registered.",
                    })
                else:
                    try:
                        result = dispatcher(tool_input)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Tool %s raised an exception", tool_name)
                        result = {
                            "ok": False,
                            "isError": True,
                            "code": "TOOL_EXCEPTION",
                            "guidance": str(exc),
                        }

                    # Update hook_context after get_user_context returns
                    if tool_name == "get_user_context" and result.get("ok"):
                        account_status: str = (
                            result.get("data", {}).get("account_status", "")
                        )
                        hook_context["account_status"] = account_status
                        vip: bool = result.get("data", {}).get("vip", False)
                        if vip:
                            hook_context["vip"] = "true"

                    if tool_name == "reset_user_password":
                        if result.get("ok"):
                            reset_executed = True
                        elif result.get("isError"):
                            code = result.get("code", "")
                            if code in ("ACCOUNT_FROZEN", "HOOK_BLOCKED"):
                                reset_blocked = True
                                escalated = True

                    if tool_name == "resolve_ticket" and result.get("ok"):
                        ticket_resolved = True
                        if not ticket_id:
                            ticket_id = tool_input.get("ticket_id")

                    tool_result_content = json.dumps(result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_result_content,
                })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — break safely
        logger.warning("Unexpected stop_reason=%s", response.stop_reason)
        break

    # --- Determine outcome ---
    if not final_text:
        # Try to get text from the last assistant message in history
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    parts = [b.text for b in content if hasattr(b, "text") and b.text]
                    if parts:
                        final_text = "\n".join(parts).strip()
                        break
                elif isinstance(content, str):
                    final_text = content
                    break

    # Determine escalation from VIP flag in hook_context
    if hook_context.get("vip") == "true":
        escalated = True

    if reset_executed and ticket_resolved and not escalated:
        action_taken = "auto_resolved"
        routing_target = "PasswordResetSpecialist"
        resolution_summary = final_text or "Password reset completed and ticket resolved."
    elif escalated or reset_blocked:
        action_taken = "escalated"
        routing_target = "human_operator"
        resolution_summary = final_text or "Escalated due to account restrictions or policy block."
    elif reset_executed and not ticket_resolved:
        action_taken = "auto_resolved"
        routing_target = "PasswordResetSpecialist"
        resolution_summary = final_text or "Password reset completed."
    else:
        action_taken = "failed"
        routing_target = "human_operator"
        escalated = True
        resolution_summary = final_text or "Unable to complete password reset."

    logger.info(
        "PasswordResetSpecialist finished",
        extra={
            "action_taken": action_taken,
            "escalated": escalated,
            "ticket_id": ticket_id,
            "routing_target": routing_target,
            "priority": priority,
            "reset_executed": reset_executed,
            "reset_blocked": reset_blocked,
            "ticket_resolved": ticket_resolved,
        },
    )

    return {
        "action_taken": action_taken,
        "escalated": escalated,
        "ticket_id": ticket_id,
        "resolution_summary": resolution_summary,
        "routing_target": routing_target,
        "reasoning": final_text,
    }
