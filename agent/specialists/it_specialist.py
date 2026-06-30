"""ITSpecialistAgent — handles non-password IT incidents.

Auto-resolves ONLY P3/P4 tickets with an unambiguous KB match (solution_type="self_service").
Escalates on: P1, P2 + write actions, VIP users, legal/compliance mentions, security breach keywords.

Does NOT inherit coordinator context — all relevant fields must be passed
explicitly in the task_prompt (ticket body, priority, category, user context, ticket_id).
"""
from __future__ import annotations

import json
import logging
import re

import anthropic

from agent.hooks import pre_tool_use_hook
from agent.tools.create_or_update_ticket import create_or_update_ticket
from agent.tools.escalate import escalate
from agent.tools.get_user_context import get_user_context
from agent.tools.lookup_kb import lookup_kb
from agent.tools.resolve_ticket import resolve_ticket

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 15

ALWAYS_ESCALATE_KEYWORDS = ["breach", "ransomware", "exfil", "data leak", "compromise"]

SYSTEM_PROMPT = """You are the ITSpecialistAgent. You handle non-password IT incidents.
Auto-resolve ONLY P3/P4 tickets with an unambiguous KB match (solution_type="self_service").
ALWAYS escalate: P1, P2 + write actions, VIP users, legal/compliance mentions, security breach keywords.
Call create_or_update_ticket to create/update the ticket.
Call escalate for any situation requiring human attention.
Call resolve_ticket only for clear P3/P4 self-service cases with KB solution."""

TOOLS: list[dict] = [
    {
        "name": "get_user_context",
        "description": (
            "Look up a user's role, department, account status, VIP flag, and recent tickets. "
            "Call this first to check if the requester is VIP or if the account is frozen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user ID of the requester.",
                }
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "lookup_kb",
        "description": (
            "Search the knowledge base for articles matching the issue. "
            "Returns up to 3 articles with solution_type and priority_hint. "
            "An empty result means no self-service fix exists — escalate instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language or keyword search describing the issue.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional coordinator category to narrow results.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_or_update_ticket",
        "description": (
            "Create a new ticket (ticket_id=null) or update an existing one. "
            "Must be called before escalate or resolve_ticket."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": ["string", "null"],
                    "description": "Existing ticket ID to update, or null to create a new ticket.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["P1", "P2", "P3", "P4"],
                    "description": "Ticket priority.",
                },
                "queue": {
                    "type": "string",
                    "enum": [
                        "network",
                        "software",
                        "hardware",
                        "access",
                        "security",
                        "password_reset",
                        "vip_escalation",
                    ],
                    "description": "Target queue for the ticket.",
                },
                "category": {
                    "type": "string",
                    "description": "Domain category of the issue.",
                },
                "summary": {
                    "type": "string",
                    "description": "Short description of the issue.",
                },
                "requester_id": {
                    "type": "string",
                    "description": "User ID of the person who filed the request.",
                },
                "original_input": {
                    "type": "string",
                    "description": "Optional verbatim original request text.",
                },
            },
            "required": ["ticket_id", "priority", "queue", "category", "summary", "requester_id"],
        },
    },
    {
        "name": "resolve_ticket",
        "description": (
            "Close a ticket with a resolution summary. "
            "Only call for P3/P4 tickets with a confirmed self-service KB solution. "
            "Hard-blocked for P1 tickets by the hook layer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "The ticket ID to resolve.",
                },
                "resolution_summary": {
                    "type": "string",
                    "description": "Plain-language summary of how the issue was resolved.",
                },
            },
            "required": ["ticket_id", "resolution_summary"],
        },
    },
    {
        "name": "escalate",
        "description": (
            "Flag a ticket for human review. "
            "Call for P1 incidents, P2 + write actions, VIP users, legal/compliance mentions, "
            "security breach keywords, or any situation where confidence < 0.75."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "The ticket ID to escalate.",
                },
                "reason": {
                    "type": "string",
                    "description": "Plain-language escalation reason.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Escalation severity.",
                },
                "impact": {
                    "type": "string",
                    "description": "Short description of the business impact.",
                },
            },
            "required": ["ticket_id", "reason", "severity", "impact"],
        },
    },
]


def _contains_escalate_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in ALWAYS_ESCALATE_KEYWORDS)


def _extract_priority_from_prompt(task_prompt: str) -> str | None:
    match = re.search(r"\b(P[1-4])\b", task_prompt)
    return match.group(1) if match else None


def _dispatch_tool(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "get_user_context":
        return get_user_context(**tool_input)
    if tool_name == "lookup_kb":
        return lookup_kb(**tool_input)
    if tool_name == "create_or_update_ticket":
        return create_or_update_ticket(**tool_input)
    if tool_name == "resolve_ticket":
        return resolve_ticket(**tool_input)
    if tool_name == "escalate":
        return escalate(**tool_input)
    return {
        "ok": False,
        "isError": True,
        "code": "UNKNOWN_TOOL",
        "guidance": f"Tool '{tool_name}' is not registered.",
    }


def run(task_prompt: str) -> dict:
    """Run the ITSpecialistAgent on the given task prompt.

    Returns a dict with keys:
      action_taken  : "auto_resolved" | "escalated" | "ticket_created" | "failed"
      escalated     : bool
      ticket_id     : str | None
      routing_target: str
      reasoning     : str
    """
    client = anthropic.Anthropic()

    messages: list[dict] = [{"role": "user", "content": task_prompt}]

    # Eagerly check for always-escalate keywords in the prompt itself
    prompt_has_breach_keyword = _contains_escalate_keyword(task_prompt)
    priority_from_prompt = _extract_priority_from_prompt(task_prompt)

    # Track state across agentic loop
    ticket_id: str | None = None
    action_taken = "failed"
    escalated = False
    routing_target = "it_specialist"
    reasoning = ""
    account_status: str = ""

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,  # type: ignore[arg-type]
            messages=messages,
        )

        stop_reason = response.stop_reason

        if stop_reason == "max_tokens":
            logger.warning(
                "ITSpecialistAgent hit max_tokens at iteration %d",
                iteration,
            )
            break

        if stop_reason == "end_turn":
            # Collect final text reasoning if present
            for block in response.content:
                if hasattr(block, "text"):
                    reasoning = block.text
            break

        if stop_reason == "tool_use":
            # Append assistant message with all content blocks
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name: str = block.name
                tool_input: dict = block.input
                tool_use_id: str = block.id

                # Build hook context from what we know so far
                hook_context: dict = {
                    "priority": priority_from_prompt,
                    "account_status": account_status,
                }

                # Run pre-tool-use hook
                block_response = pre_tool_use_hook(tool_name, tool_input, hook_context)
                if block_response is not None:
                    logger.warning(
                        "PreToolUse hook blocked tool '%s': %s",
                        tool_name,
                        block_response.get("reason"),
                    )
                    tool_result_content = json.dumps({
                        "ok": False,
                        "isError": True,
                        "code": "HOOK_BLOCKED",
                        "guidance": block_response.get("reason", "Tool call blocked by policy."),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": tool_result_content,
                    })
                    continue

                # Force-block resolve if breach keyword found in prompt
                if prompt_has_breach_keyword and tool_name == "resolve_ticket":
                    logger.warning(
                        "Blocking resolve_ticket — always-escalate keyword detected in prompt",
                    )
                    tool_result_content = json.dumps({
                        "ok": False,
                        "isError": True,
                        "code": "HOOK_BLOCKED",
                        "guidance": (
                            "Security breach keyword detected; auto-resolution is not allowed. "
                            "Call escalate instead."
                        ),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": tool_result_content,
                    })
                    continue

                # Execute the tool
                result = _dispatch_tool(tool_name, tool_input)

                # Update local state from tool results
                if tool_name == "get_user_context" and result.get("ok"):
                    data = result.get("data", {})
                    account_status = data.get("account_status", "")

                if tool_name == "create_or_update_ticket" and result.get("ok"):
                    ticket_id = result["data"]["ticket_id"]
                    action_taken = "ticket_created"
                    resolved_priority = result["data"].get("priority")
                    if resolved_priority:
                        priority_from_prompt = resolved_priority

                if tool_name == "resolve_ticket" and result.get("ok"):
                    action_taken = "auto_resolved"
                    routing_target = "resolved"

                if tool_name == "escalate" and result.get("ok"):
                    action_taken = "escalated"
                    escalated = True
                    routing_target = "human_operator"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result),
                })

            # Append all tool results as a single user message
            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop_reason — break to avoid infinite loop
            logger.warning(
                "Unexpected stop_reason '%s' at iteration %d",
                stop_reason,
                iteration,
            )
            break

    # Derive final reasoning from last assistant text block if not already set
    if not reasoning:
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if hasattr(block, "text") and block.text:
                            reasoning = block.text
                            break
                elif isinstance(content, str):
                    reasoning = content
                if reasoning:
                    break

    logger.info(
        "ITSpecialistAgent completed: action=%s escalated=%s ticket=%s",
        action_taken,
        escalated,
        ticket_id,
    )

    return {
        "action_taken": action_taken,
        "escalated": escalated,
        "ticket_id": ticket_id,
        "routing_target": routing_target,
        "reasoning": reasoning,
    }
