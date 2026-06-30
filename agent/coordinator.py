"""Coordinator agent — classifies, enriches, and routes inbound IT requests.

Flow:
  1. Classify priority (P1–P4) and category
  2. Enrich with user context (pre-fetch from tools)
  3. Validate output against schema; retry up to MAX_RETRIES on failure
  4. Route to the appropriate specialist via Task prompt (explicit context pass-through)

Logged per request: category, confidence, routing, reasoning, requires_human, retry_count
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Literal

import anthropic
from pydantic import BaseModel, field_validator, ValidationError

from agent.hooks import pre_tool_use_hook
from agent.tools.get_user_context import get_user_context
from agent.tools.lookup_kb import lookup_kb
from agent.tools.create_or_update_ticket import create_or_update_ticket
from agent.tools.escalate import escalate
from agent.specialists import password_reset
from agent.specialists import it_specialist

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

ESCALATION_RULES = {
    "categories": ["legal", "compliance", "vip_escalation"],
    "min_confidence": 0.75,
    "max_dollar_impact": 10_000,
}

LEGAL_KEYWORDS: set[str] = {"legal", "compliance", "audit", "gdpr", "datenschutz", "lawsuit", "klage"}
BREACH_KEYWORDS: set[str] = {"breach", "ransomware", "exfil", "data leak", "compromise", "exfiltrat"}

VALID_QUEUES: set[str] = {
    "network", "software", "hardware", "access", "security", "password_reset", "vip_escalation"
}

MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------

class TriageResult(BaseModel):
    category: Literal[
        "password_reset", "network", "software", "hardware",
        "access", "security", "vip_escalation", "unknown"
    ]
    priority: Literal["P1", "P2", "P3", "P4"]
    confidence: float
    requires_human: bool
    escalation_reason: str | None = None
    routing_target: Literal["password_reset_specialist", "it_specialist", "human_escalation"]
    reasoning: str
    user_id: str | None = None

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v


# ---------------------------------------------------------------------------
# Tool definitions for the agentic loop
# ---------------------------------------------------------------------------

TOOL_GET_USER_CONTEXT: dict = {
    "name": "get_user_context",
    "description": (
        "Look up a user's role, department, account status, VIP flag, and recent tickets. "
        "Use this to determine if the user is a VIP or has a flagged account before routing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The unique identifier of the user to look up."
            }
        },
        "required": ["user_id"]
    }
}

TOOL_LOOKUP_KB: dict = {
    "name": "lookup_kb",
    "description": (
        "Search the IT knowledge base for articles, runbooks, or known solutions matching the request. "
        "Use this to check for self-service solutions and enrich the specialist task prompt."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language or keyword search query."
            },
            "category": {
                "type": "string",
                "description": "Optional category to narrow results (e.g. 'network', 'software').",
                "enum": [
                    "password_reset", "network", "software", "hardware",
                    "access", "security", "vip_escalation", "unknown"
                ]
            }
        },
        "required": ["query"]
    }
}

TOOL_CLASSIFY_REQUEST: dict = {
    "name": "classify_request",
    "description": (
        "Record your final classification decision for the IT request. "
        "You MUST call this tool once after gathering context. "
        "Do NOT call it until you have enough information to make a confident decision."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "The request category.",
                "enum": [
                    "password_reset", "network", "software", "hardware",
                    "access", "security", "vip_escalation", "unknown"
                ]
            },
            "priority": {
                "type": "string",
                "description": "P1=critical/outage, P2=major degradation, P3=moderate, P4=minor/cosmetic.",
                "enum": ["P1", "P2", "P3", "P4"]
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in this classification, between 0.0 and 1.0.",
                "minimum": 0.0,
                "maximum": 1.0
            },
            "requires_human": {
                "type": "boolean",
                "description": "True if this request requires human review before any action is taken."
            },
            "escalation_reason": {
                "type": "string",
                "description": "If requires_human is true, explain why escalation is needed."
            },
            "routing_target": {
                "type": "string",
                "description": "Where to route this request.",
                "enum": ["password_reset_specialist", "it_specialist", "human_escalation"]
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this classification was chosen."
            },
            "user_id": {
                "type": "string",
                "description": "The user_id if known or extracted from the request."
            }
        },
        "required": [
            "category", "priority", "confidence", "requires_human",
            "routing_target", "reasoning"
        ]
    }
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the IT Helpdesk Coordinator for adesso. Your job is to classify, enrich, and route inbound IT support requests.

## Categories
- password_reset: Password forgotten, account locked, credential issues
- network: WiFi, VPN, connectivity, DNS, proxy issues
- software: Application crashes, installation, licensing, updates
- hardware: Laptop, printer, monitor, peripheral issues
- access: Permissions, file access, Active Directory, group memberships
- security: Malware, phishing, suspicious activity, data breach
- vip_escalation: C-Level, Board members, VIP users requiring special handling
- unknown: Cannot determine category with confidence

## Priorities — base on ACTUAL business impact, never on urgency language used by the requester
- P1: Critical — complete outage, production down for many users, active security breach
- P2: Major — a whole TEAM or department is blocked; significant business degradation
- P3: Moderate — ONE individual user is blocked, no workaround exists (e.g. locked out, app crashing)
- P4: Routine — single user, self-service eligible, low business impact
        Examples: forgotten password, sticky mouse, printer offline, Teams audio, monitor settings

IMPORTANT priority rules:
- A forgotten or expired password for a single user = P4 (routine self-service, auto-resolution candidate).
  Only raise to P3 if there is a specific complication: MFA lost, account locked by security team, service account.
- NEVER assign P2 to a single-user issue. P2 requires a team or business unit to be blocked.
- Ignore urgency words like "URGENT" or "ASAP" from the requester — classify on facts only.

## Your workflow
1. Optionally call get_user_context if a user_id is available to check VIP status and account health
2. Optionally call lookup_kb to find relevant knowledge base articles
3. ALWAYS call classify_request with your final decision

## Escalation triggers (you should set requires_human=True and routing_target="human_escalation")
- User is VIP (C-Level, Board, or vip=True from get_user_context)
- Request mentions legal/compliance/GDPR/lawsuit keywords
- Request mentions security breach, ransomware, data exfiltration
- Confidence < 0.75
- Category is vip_escalation or unknown

## Routing
- password_reset category → routing_target="password_reset_specialist" (only for active, non-flagged accounts)
- All other categories → routing_target="it_specialist"
- Any escalation trigger → routing_target="human_escalation"

Be concise, accurate, and always call classify_request at the end."""


# ---------------------------------------------------------------------------
# Language heuristic
# ---------------------------------------------------------------------------

def _is_non_de_en(text: str) -> bool:
    """Heuristic: returns True if text appears to be neither German nor English."""
    # Common German and English stop words / patterns
    de_en_patterns = re.compile(
        r"\b(the|a|an|is|are|was|were|have|has|my|ich|mein|meine|nicht|bitte|"
        r"habe|kann|es|ist|das|ein|eine|ich|und|oder|aber|mit|von|zu|bei|wie|"
        r"please|need|help|my|can|not|don't|doesn't|won't|I|we|you|your|"
        r"problem|issue|error|fix|broken|doesn't|can't)\b",
        re.IGNORECASE
    )
    words = text.split()
    if len(words) < 4:
        return False
    matches = len(de_en_patterns.findall(text))
    # If fewer than 10% of words match common DE/EN patterns, consider it foreign
    return matches < max(1, len(words) * 0.1)


# ---------------------------------------------------------------------------
# Priority to severity mapping
# ---------------------------------------------------------------------------

def _priority_to_severity(priority: str) -> str:
    return {
        "P1": "critical",
        "P2": "high",
        "P3": "medium",
        "P4": "low",
    }.get(priority, "medium")


# ---------------------------------------------------------------------------
# Main coordinator function
# ---------------------------------------------------------------------------

def run_coordinator(request_text: str, user_id: str | None = None) -> dict:
    """Classify, enrich, and route a single inbound IT request."""
    request_id = str(uuid.uuid4())[:8]
    retry_count = 0
    hook_blocked = False
    user_context: dict | None = None
    kb_articles: list[dict] = []
    classify_input: dict | None = None

    client = anthropic.Anthropic()

    # Build initial user message
    user_message = request_text
    if user_id:
        user_message = f"[user_id: {user_id}]\n{request_text}"

    messages: list[dict] = [{"role": "user", "content": user_message}]

    # ------------------------------------------------------------------
    # Agentic loop
    # ------------------------------------------------------------------
    max_iterations = 20
    iteration = 0

    while iteration < max_iterations and classify_input is None:
        iteration += 1

        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[TOOL_GET_USER_CONTEXT, TOOL_LOOKUP_KB, TOOL_CLASSIFY_REQUEST],
            messages=messages,
        )

        if response.stop_reason == "max_tokens":
            logger.warning({"event": "coordinator_max_tokens", "request_id": request_id, "iteration": iteration})
            break

        if response.stop_reason == "end_turn":
            # Try to extract JSON from text as a last resort
            for block in response.content:
                if hasattr(block, "text"):
                    try:
                        json_match = re.search(r"\{.*\}", block.text, re.DOTALL)
                        if json_match:
                            classify_input = json.loads(json_match.group())
                    except (json.JSONDecodeError, AttributeError):
                        pass

            if classify_input is not None:
                break

            # Model stopped without calling classify_request — nudge it explicitly
            if iteration < max_iterations - 1:
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": (
                        "You did not call classify_request. "
                        "You MUST call classify_request now with your classification decision. "
                        "Do not respond with text — call the tool."
                    ),
                })
                continue

            break

        if response.stop_reason == "tool_use":
            tool_results: list[dict] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                # Check pre_tool_use_hook
                hook_context: dict = {}
                if user_context and user_context.get("ok") and user_context.get("data"):
                    hook_context["account_status"] = user_context["data"].get("account_status", "")
                hook_result = pre_tool_use_hook(tool_name, tool_input, hook_context)

                if hook_result and hook_result.get("block"):
                    hook_blocked = True
                    logger.warning({
                        "event": "tool_blocked",
                        "request_id": request_id,
                        "tool": tool_name,
                        "reason": hook_result.get("reason"),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({
                            "ok": False,
                            "isError": True,
                            "code": "BLOCKED_BY_HOOK",
                            "guidance": hook_result.get("reason", "Tool call blocked by pre-tool-use hook."),
                        }),
                    })
                    continue

                if tool_name == "get_user_context":
                    uid = tool_input.get("user_id", "")
                    result = get_user_context(uid)
                    if result.get("ok") and result.get("data"):
                        user_context = result
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(result),
                    })

                elif tool_name == "lookup_kb":
                    query = tool_input.get("query", "")
                    category = tool_input.get("category")
                    result = lookup_kb(query, category)
                    if result.get("ok") and result.get("data", {}).get("articles"):
                        kb_articles = result["data"]["articles"]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(result),
                    })

                elif tool_name == "classify_request":
                    classify_input = dict(tool_input)
                    # Still need to provide a tool result so messages stay valid
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({"ok": True, "data": {"recorded": True}}),
                    })
                    # Break out after collecting classify_input
                    break

            # Append assistant turn + tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # If we got the classification, exit the loop
            if classify_input is not None:
                break

    # ------------------------------------------------------------------
    # Validation-retry loop
    # ------------------------------------------------------------------
    triage_result: TriageResult | None = None

    if classify_input is None:
        # Fallback: create a minimal classify_input so we can proceed
        classify_input = {
            "category": "unknown",
            "priority": "P3",
            "confidence": 0.0,
            "requires_human": True,
            "escalation_reason": "Coordinator failed to produce a classification.",
            "routing_target": "human_escalation",
            "reasoning": "No classification was produced by the agentic loop.",
        }

    for attempt in range(MAX_RETRIES):
        try:
            triage_result = TriageResult(**classify_input)
            break
        except ValidationError as exc:
            retry_count = attempt + 1
            error_type = type(exc).__name__
            logger.warning({
                "event": "validation_retry",
                "request_id": request_id,
                "retry_count": retry_count,
                "error_type": error_type,
                "errors": exc.errors(),
            })

            if attempt < MAX_RETRIES - 1:
                # Ask Claude to fix the classification
                feedback_message = (
                    f"The classify_request call failed validation with these errors:\n"
                    f"{exc.errors()}\n\n"
                    f"Please call classify_request again with valid values."
                )
                messages.append({"role": "user", "content": feedback_message})

                # Run one more iteration to get a corrected classify_input
                classify_input = None
                inner_iterations = 0
                while inner_iterations < 5 and classify_input is None:
                    inner_iterations += 1
                    resp = client.messages.create(
                        model=MODEL,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        tools=[TOOL_GET_USER_CONTEXT, TOOL_LOOKUP_KB, TOOL_CLASSIFY_REQUEST],
                        messages=messages,
                    )
                    if resp.stop_reason == "tool_use":
                        tool_results2: list[dict] = []
                        for block in resp.content:
                            if block.type != "tool_use":
                                continue
                            if block.name == "classify_request":
                                classify_input = dict(block.input)
                                tool_results2.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps({"ok": True, "data": {"recorded": True}}),
                                })
                                break
                            else:
                                # Handle other tools minimally
                                tool_results2.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps({"ok": True, "data": {}}),
                                })
                        messages.append({"role": "assistant", "content": resp.content})
                        if tool_results2:
                            messages.append({"role": "user", "content": tool_results2})
                    else:
                        break

                if classify_input is None:
                    classify_input = {
                        "category": "unknown",
                        "priority": "P3",
                        "confidence": 0.0,
                        "requires_human": True,
                        "escalation_reason": "Validation failed after retry.",
                        "routing_target": "human_escalation",
                        "reasoning": "Classification could not be validated.",
                    }
            else:
                # Final fallback after all retries exhausted
                triage_result = TriageResult(
                    category="unknown",
                    priority="P3",
                    confidence=0.0,
                    requires_human=True,
                    escalation_reason="Validation failed after all retries.",
                    routing_target="human_escalation",
                    reasoning="Classification could not be validated after maximum retries.",
                    user_id=user_id,
                )

    if triage_result is None:
        triage_result = TriageResult(
            category="unknown",
            priority="P3",
            confidence=0.0,
            requires_human=True,
            escalation_reason="Coordinator failed to produce a valid classification.",
            routing_target="human_escalation",
            reasoning="No valid classification produced.",
            user_id=user_id,
        )

    # ------------------------------------------------------------------
    # Post-validation escalation overrides (deterministic)
    # ------------------------------------------------------------------
    request_lower = request_text.lower()

    # Confidence threshold
    if triage_result.confidence < 0.75:
        triage_result.requires_human = True
        triage_result.routing_target = "human_escalation"
        if not triage_result.escalation_reason:
            triage_result.escalation_reason = f"Confidence {triage_result.confidence:.2f} below threshold 0.75"

    # Legal keywords
    if any(kw in request_lower for kw in LEGAL_KEYWORDS):
        triage_result.requires_human = True
        triage_result.routing_target = "human_escalation"
        triage_result.escalation_reason = (triage_result.escalation_reason or "") + " Legal/compliance keyword detected."

    # Breach / security keywords
    if any(kw in request_lower for kw in BREACH_KEYWORDS):
        triage_result.requires_human = True
        triage_result.routing_target = "human_escalation"
        triage_result.priority = "P1"
        triage_result.escalation_reason = (triage_result.escalation_reason or "") + " Security breach keyword detected."

    # VIP user check
    if user_context and user_context.get("ok") and user_context.get("data"):
        if user_context["data"].get("vip"):
            triage_result.requires_human = True
            triage_result.routing_target = "human_escalation"
            triage_result.escalation_reason = (triage_result.escalation_reason or "") + " VIP user."

    # Category-based escalation
    if triage_result.category in ("vip_escalation", "unknown"):
        triage_result.requires_human = True
        triage_result.routing_target = "human_escalation"
        if not triage_result.escalation_reason:
            triage_result.escalation_reason = f"Category '{triage_result.category}' requires human review."

    # Language heuristic
    if _is_non_de_en(request_text):
        triage_result.requires_human = True
        triage_result.routing_target = "human_escalation"
        triage_result.escalation_reason = (triage_result.escalation_reason or "") + " Non-DE/EN language detected."

    # ------------------------------------------------------------------
    # Create ticket
    # ------------------------------------------------------------------
    queue = triage_result.category if triage_result.category in VALID_QUEUES else "vip_escalation"
    ticket_result = create_or_update_ticket(
        ticket_id=None,
        priority=triage_result.priority,
        queue=queue,
        category=triage_result.category,
        summary=request_text[:120],
        requester_id=user_id or "unknown",
        original_input=request_text,
    )

    ticket_id: str | None = None
    if ticket_result.get("ok") and ticket_result.get("data"):
        ticket_id = ticket_result["data"]["ticket_id"]
    else:
        logger.error({
            "event": "ticket_creation_failed",
            "request_id": request_id,
            "error": ticket_result,
        })
        ticket_id = f"fallback-{request_id}"

    # ------------------------------------------------------------------
    # Route: escalate or dispatch to specialist
    # ------------------------------------------------------------------
    action_taken: str = "unknown"

    if triage_result.requires_human:
        severity = _priority_to_severity(triage_result.priority)
        impact = (
            triage_result.escalation_reason
            or f"Request requires human review (category={triage_result.category}, priority={triage_result.priority})"
        )
        if ticket_id:
            escalate_result = escalate(
                ticket_id=ticket_id,
                reason=triage_result.escalation_reason or "Escalation triggered by coordinator.",
                severity=severity,
                impact=impact,
            )
            if escalate_result.get("ok"):
                action_taken = "escalated_to_human"
            else:
                action_taken = "escalation_failed"
                logger.error({
                    "event": "escalation_failed",
                    "request_id": request_id,
                    "error": escalate_result,
                })
        else:
            action_taken = "escalated_to_human"
    else:
        # Build task prompt for specialist
        task_prompt_parts = [
            "## IT Request",
            f"**Original Request:** {request_text}",
            f"**Category:** {triage_result.category}",
            f"**Priority:** {triage_result.priority}",
            f"**Confidence:** {triage_result.confidence:.2f}",
            f"**Ticket ID:** {ticket_id}",
            f"**Reasoning:** {triage_result.reasoning}",
        ]
        if user_id:
            task_prompt_parts.append(f"**User ID:** {user_id}")
        if user_context and user_context.get("ok") and user_context.get("data"):
            task_prompt_parts.append(f"**User Context:** {json.dumps(user_context['data'])}")
        if kb_articles:
            task_prompt_parts.append("**Knowledge Base Articles:**")
            for article in kb_articles:
                task_prompt_parts.append(
                    f"  - [{article.get('id')}] {article.get('title')}: {article.get('body', '')[:200]}"
                )

        task_prompt = "\n".join(task_prompt_parts)

        try:
            if triage_result.routing_target == "password_reset_specialist":
                specialist_result = password_reset.run(task_prompt)
                action_taken = specialist_result.get("action_taken", "routed_to_password_reset_specialist")
            else:
                specialist_result = it_specialist.run(task_prompt)
                action_taken = specialist_result.get("action_taken", "routed_to_it_specialist")
        except NotImplementedError:
            action_taken = f"queued_for_{triage_result.routing_target}"
        except Exception as exc:
            logger.error({
                "event": "specialist_error",
                "request_id": request_id,
                "routing_target": triage_result.routing_target,
                "error": str(exc),
            })
            action_taken = "specialist_error"

    # ------------------------------------------------------------------
    # Log structured decision
    # ------------------------------------------------------------------
    logger.info({
        "event": "coordinator_decision",
        "request_id": request_id,
        "channel": "api",
        "category": triage_result.category,
        "priority": triage_result.priority,
        "confidence": triage_result.confidence,
        "routing_target": triage_result.routing_target,
        "retry_count": retry_count,
        "error_type": None,
        "escalated": triage_result.requires_human,
        "hook_blocked": hook_blocked,
        "ticket_id": ticket_id,
        "action_taken": action_taken,
    })

    return {
        "request_id": request_id,
        "category": triage_result.category,
        "priority": triage_result.priority,
        "confidence": triage_result.confidence,
        "escalated": triage_result.requires_human,
        "ticket_id": ticket_id,
        "action_taken": action_taken,
        "routing_target": triage_result.routing_target,
        "reasoning": triage_result.reasoning,
        "requires_human": triage_result.requires_human,
        "retry_count": retry_count,
    }
