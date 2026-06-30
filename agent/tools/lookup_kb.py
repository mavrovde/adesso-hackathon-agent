"""Tool: lookup_kb

Searches the knowledge base for articles matching the query.
Returns the top 3 matches ranked by tag overlap + title match.
Does NOT return articles for categories outside IT helpdesk.

When to use:
  - Before routing a request, to check for self-service solutions
  - To enrich the Specialist-Agent Task prompt with known runbooks

What this tool does NOT do:
  - Read live system data (no ITSM, no AD)
  - Return user-specific data
  - No match (empty articles list) is not an error — it means: escalate

Input:  query    (str)            — natural language or keyword search
        category (str, optional) — coordinator category; narrows results
Output: { ok: True, data: { articles: [ { id, title, body, solution_type, priority_hint } ] } }
        { ok: True, data: { articles: [] } }  — no matches is not an error
"""
from __future__ import annotations
from agent.tools.mock_store import KB_ARTICLES


def lookup_kb(query: str, category: str | None = None) -> dict:
    query_tokens = set(query.lower().split())
    pool = [a for a in KB_ARTICLES if category is None or a.get("category") == category]

    scored = []
    for article in pool:
        tag_hits = len(query_tokens & set(article["tags"]))
        title_hits = sum(1 for t in query_tokens if t in article["title"].lower())
        scored.append((tag_hits + title_hits, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [
        {
            "id": a["id"],
            "title": a["title"],
            "body": a["body"],
            "solution_type": a["solution_type"],
            "priority_hint": a["priority_hint"],
        }
        for score, a in scored
        if score > 0
    ][:3]
    return {"ok": True, "data": {"articles": top}}
