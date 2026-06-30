"""In-memory mock store — simulates the ticketing system and user directory.

All state is module-level so it persists across tool calls within one run.
Reset by calling reset_store() between test cases.
"""
from __future__ import annotations
import uuid

# ---------------------------------------------------------------------------
# User directory
# ---------------------------------------------------------------------------

USERS: dict[str, dict] = {
    "u001": {
        "user_id": "u001",
        "name": "Alice Müller",
        "role": "Software Engineer",
        "department": "Engineering",
        "account_status": "ACTIVE",
        "vip": False,
        "recent_tickets": [],
    },
    "u002": {
        "user_id": "u002",
        "name": "Bob Schmidt",
        "role": "VP of Sales",
        "department": "Sales",
        "account_status": "ACTIVE",
        "vip": True,
        "recent_tickets": [],
    },
    "u003": {
        "user_id": "u003",
        "name": "Carol Weber",
        "role": "Accountant",
        "department": "Finance",
        "account_status": "FROZEN",
        "vip": False,
        "recent_tickets": [],
    },
}

# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------

KB_ARTICLES: list[dict] = [
    {
        "id": "kb-001",
        "title": "Password reset — Active Directory",
        "tags": ["password", "ad", "reset"],
        "body": "Use the AD self-service portal at https://internal/password-reset. Temporary password expires in 24 h.",
    },
    {
        "id": "kb-002",
        "title": "VPN connectivity issues",
        "tags": ["vpn", "network", "connectivity"],
        "body": "Restart the VPN client. If the issue persists, flush DNS (ipconfig /flushdns) and reconnect.",
    },
    {
        "id": "kb-003",
        "title": "WiFi not connecting — laptop",
        "tags": ["wifi", "network", "laptop"],
        "body": "Forget the network and reconnect. Check that the NIC driver is up to date via Device Manager.",
    },
]

# ---------------------------------------------------------------------------
# Ticket store
# ---------------------------------------------------------------------------

TICKETS: dict[str, dict] = {}


def create_ticket(body: dict) -> dict:
    ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
    ticket = {"ticket_id": ticket_id, "status": "OPEN", **body}
    TICKETS[ticket_id] = ticket
    return ticket


def reset_store() -> None:
    """Reset all mutable state — call between test cases."""
    TICKETS.clear()
    for user in USERS.values():
        user["recent_tickets"] = []
