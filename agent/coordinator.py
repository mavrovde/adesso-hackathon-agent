"""Coordinator agent — classifies, enriches, and routes inbound IT requests.

Flow:
  1. Classify priority (P1–P4) and category
  2. Enrich with user context (pre-fetch from tools)
  3. Validate output against schema; retry up to MAX_RETRIES on failure
  4. Route to the appropriate specialist via Task prompt (explicit context pass-through)

Logged per request: category, confidence, routing, reasoning, requires_human, retry_count
"""
from __future__ import annotations

# TODO: implement with Claude Agent SDK
#   - structured output with validation-retry loop (max 3 retries)
#   - explicit context handoff in each Task prompt
#   - log reasoning chain so every decision is replayable

MAX_RETRIES = 3

ESCALATION_RULES = {
    "categories": ["legal", "compliance", "vip_escalation"],
    "min_confidence": 0.75,
    "max_dollar_impact": 10_000,
}


def run_coordinator(request_text: str) -> dict:
    """Classify, enrich, and route a single inbound IT request."""
    raise NotImplementedError
