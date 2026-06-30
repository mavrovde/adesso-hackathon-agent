"""Tool: lookup_kb

Searches the knowledge base for articles matching the query.
Returns the top 3 matches ranked by tag overlap.
Does NOT return articles for categories outside IT helpdesk.

Input:  query (str) — natural language or keyword search
Output: { ok: true, data: { articles: [ { id, title, body } ] } }
        { ok: true, data: { articles: [] } }  — no matches is not an error
"""
from __future__ import annotations
from agent.tools.mock_store import KB_ARTICLES


def lookup_kb(query: str) -> dict:
    query_tokens = set(query.lower().split())
    scored = []
    for article in KB_ARTICLES:
        tag_hits = len(query_tokens & set(article["tags"]))
        title_hits = sum(1 for t in query_tokens if t in article["title"].lower())
        scored.append((tag_hits + title_hits, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [a for score, a in scored if score > 0][:3]
    return {"ok": True, "data": {"articles": top}}
