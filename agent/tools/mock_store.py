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
# Schema per entry:
#   id            — unique reference, logged with every routing decision
#   category      — matches coordinator categories; used for filtered lookup
#   title         — short description; feeds into title-scoring
#   tags          — German AND English keywords; primary match mechanism
#   body          — solution steps or escalation note; inserted into Task prompts
#   solution_type — self_service | it_specialist | escalate_always
#   priority_hint — recommended priority; coordinator may override

KB_ARTICLES: list[dict] = [
    # ------------------------------------------------------------------
    # password_reset (5)
    # ------------------------------------------------------------------
    {
        "id": "kb-001",
        "category": "password_reset",
        "title": "Password reset — Active Directory",
        "tags": ["password", "passwort", "ad", "active directory", "reset", "vergessen", "forgot"],
        "body": "Open the AD self-service portal at https://internal/password-reset. The temporary password expires in 24 h. If the account is locked, check 'Unlock account' on the same page.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-002",
        "category": "password_reset",
        "title": "Password reset — SSO / SAML",
        "tags": ["sso", "saml", "single sign-on", "password", "passwort", "reset", "okta", "azure ad"],
        "body": "SSO passwords are managed via the identity provider (Okta / Azure AD). Go to https://internal/sso-reset and follow the self-service flow. MFA must be available to complete the reset.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-003",
        "category": "password_reset",
        "title": "MFA second factor lost or unavailable",
        "tags": ["mfa", "2fa", "authenticator", "second factor", "zweiter faktor", "token", "otp"],
        "body": "MFA resets require identity verification by 1st-Level Helpdesk. Raise a ticket — IT will verify identity via employee ID and manager confirmation before resetting the MFA device.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    {
        "id": "kb-004",
        "category": "password_reset",
        "title": "Service account password reset",
        "tags": ["service account", "dienstkonto", "password", "passwort", "reset", "api", "automation"],
        "body": "Service account resets must go through the owning team's IT contact. Automated resets are NOT permitted — check the CMDB for the account owner before proceeding.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    {
        "id": "kb-005",
        "category": "password_reset",
        "title": "Account locked out after failed login attempts",
        "tags": ["locked", "gesperrt", "lockout", "too many attempts", "zu viele versuche", "account"],
        "body": "Accounts lock after 5 failed attempts. Use the AD self-service portal at https://internal/password-reset and select 'Unlock account'. If the account is flagged as FROZEN, do not unlock — escalate to Security.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    # ------------------------------------------------------------------
    # network (7)
    # ------------------------------------------------------------------
    {
        "id": "kb-010",
        "category": "network",
        "title": "VPN disconnects after standby / sleep",
        "tags": ["vpn", "disconnect", "trennt", "standby", "sleep", "schlaf", "reconnect", "cisco anyconnect"],
        "body": "Restart the VPN client via the system tray. If it does not reconnect: open Services (services.msc), restart 'Cisco AnyConnect VPN Agent'. Still failing → raise a ticket for IT Specialist.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-011",
        "category": "network",
        "title": "VPN connectivity issues — general",
        "tags": ["vpn", "network", "connectivity", "netzwerk", "verbindung", "tunnel", "remote"],
        "body": "Restart the VPN client. Flush DNS: ipconfig /flushdns (Windows) or sudo dscacheutil -flushcache (macOS). If the issue persists after reconnect, raise a ticket — include error code from VPN client logs.",
        "solution_type": "self_service",
        "priority_hint": "P3",
    },
    {
        "id": "kb-012",
        "category": "network",
        "title": "WiFi not connecting — laptop",
        "tags": ["wifi", "wlan", "network", "netzwerk", "laptop", "wireless", "kein internet", "no internet"],
        "body": "Forget the network and reconnect. Check NIC driver in Device Manager. If corporate SSID is missing: IT may need to re-push the WLAN profile via MDM.",
        "solution_type": "self_service",
        "priority_hint": "P3",
    },
    {
        "id": "kb-013",
        "category": "network",
        "title": "Proxy settings blocking access to internal sites",
        "tags": ["proxy", "network", "netzwerk", "blocked", "gesperrt", "pac", "wpad", "internal", "intern"],
        "body": "Check proxy settings: Control Panel → Internet Options → Connections → LAN Settings. PAC file URL should be http://internal/proxy.pac. If misconfigured, run the endpoint compliance script from the IT portal.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-014",
        "category": "network",
        "title": "DNS resolution failures on corporate network",
        "tags": ["dns", "network", "netzwerk", "resolution", "auflösung", "domain", "ping", "resolve"],
        "body": "Flush DNS: ipconfig /flushdns. Verify DNS servers are set to 10.0.0.1 and 10.0.0.2. If wrong: re-run the network configuration script from https://internal/it-tools.",
        "solution_type": "self_service",
        "priority_hint": "P3",
    },
    {
        "id": "kb-015",
        "category": "network",
        "title": "Remote Desktop (RDP) connection refused",
        "tags": ["rdp", "remote desktop", "fernzugriff", "connection refused", "port 3389", "windows", "server"],
        "body": "Verify the target machine is reachable (ping). Check that RDP is enabled on the target: System Properties → Remote. Firewall rule for port 3389 may need opening — raise a ticket for IT Specialist with the target hostname.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    {
        "id": "kb-016",
        "category": "network",
        "title": "Network-attached printer offline",
        "tags": ["printer", "drucker", "network", "netzwerk", "offline", "lan", "print queue"],
        "body": "Check that the printer's IP is reachable (ping). Restart the print spooler: services.msc → Print Spooler → Restart. If the printer has a static IP conflict, raise a ticket for IT Specialist.",
        "solution_type": "it_specialist",
        "priority_hint": "P4",
    },
    # ------------------------------------------------------------------
    # software (6)
    # ------------------------------------------------------------------
    {
        "id": "kb-020",
        "category": "software",
        "title": "Microsoft Office keeps crashing",
        "tags": ["office", "word", "excel", "powerpoint", "crash", "absturz", "microsoft", "not responding"],
        "body": "Run Office repair: Control Panel → Programs → Microsoft 365 → Change → Quick Repair. If crash persists after repair, run Online Repair. Collect crash dump from %LOCALAPPDATA%\\CrashDumps and attach to ticket.",
        "solution_type": "self_service",
        "priority_hint": "P3",
    },
    {
        "id": "kb-021",
        "category": "software",
        "title": "Software license expired or not activated",
        "tags": ["license", "lizenz", "activation", "aktivierung", "expired", "abgelaufen", "key", "serial"],
        "body": "Check the software asset register at https://internal/licenses. If the license is registered but not applied, re-run the license activation script. If not registered, raise a procurement request via the IT portal.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    {
        "id": "kb-022",
        "category": "software",
        "title": "Outlook profile corrupt or not loading",
        "tags": ["outlook", "email", "mail", "profile", "corrupt", "beschädigt", "ost", "pst", "not loading"],
        "body": "Create a new Outlook profile: Control Panel → Mail → Show Profiles → Add. Point it at the Exchange server (autodiscover). If the old .ost file is large (> 50 GB), archive first to avoid re-sync time.",
        "solution_type": "self_service",
        "priority_hint": "P3",
    },
    {
        "id": "kb-023",
        "category": "software",
        "title": "Microsoft Teams audio or video not working",
        "tags": ["teams", "audio", "video", "microphone", "mikrofon", "camera", "kamera", "call", "meeting"],
        "body": "In Teams Settings → Devices, verify the correct microphone and speaker are selected. Check Windows Privacy settings allow Teams microphone access. Restart the Teams app (fully quit from tray). If issue persists on all calls, raise a ticket.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-024",
        "category": "software",
        "title": "Windows Update fails or gets stuck",
        "tags": ["windows", "update", "stuck", "fehler", "error", "patch", "kb", "cumulative update"],
        "body": "Run the Windows Update troubleshooter. If it fails: net stop wuauserv, delete C:\\Windows\\SoftwareDistribution\\Download\\*, net start wuauserv, retry update. Still stuck → raise a ticket for IT Specialist.",
        "solution_type": "self_service",
        "priority_hint": "P3",
    },
    {
        "id": "kb-025",
        "category": "software",
        "title": "Antivirus flagged a file — potential malware",
        "tags": ["antivirus", "malware", "virus", "threat", "bedrohung", "quarantine", "quarantäne", "infected", "infiziert"],
        "body": "Do NOT dismiss the alert. Isolate the machine from the network (disable WiFi/LAN). Raise a P2 ticket immediately — Security team will take over. Do not attempt to restore the quarantined file.",
        "solution_type": "escalate_always",
        "priority_hint": "P2",
    },
    # ------------------------------------------------------------------
    # hardware (5)
    # ------------------------------------------------------------------
    {
        "id": "kb-030",
        "category": "hardware",
        "title": "Docking station not detected",
        "tags": ["docking", "dock", "dockingstation", "usb-c", "thunderbolt", "monitor", "peripherals", "not detected"],
        "body": "Unplug and replug the dock. Update the dock firmware via the manufacturer's utility. If using Thunderbolt: disable and re-enable Thunderbolt in BIOS. Still failing → raise a ticket — IT may need to replace the dock.",
        "solution_type": "self_service",
        "priority_hint": "P3",
    },
    {
        "id": "kb-031",
        "category": "hardware",
        "title": "External monitor shows no signal",
        "tags": ["monitor", "display", "bildschirm", "no signal", "kein signal", "hdmi", "displayport", "vga"],
        "body": "Check cable connections. Press Win+P to cycle display mode (Duplicate/Extend/Second screen). Try a different cable. If another cable works, the original cable is faulty. If no cable works, raise a ticket — hardware replacement may be needed.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-032",
        "category": "hardware",
        "title": "Local printer offline or not printing",
        "tags": ["printer", "drucker", "offline", "print", "drucken", "stuck", "queue", "warteschlange"],
        "body": "Clear the print queue: services.msc → Print Spooler → Stop → delete files in C:\\Windows\\System32\\spool\\PRINTERS\\ → Start spooler. Reinstall driver if queue is consistently stuck.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-033",
        "category": "hardware",
        "title": "Webcam not detected or showing black screen",
        "tags": ["webcam", "camera", "kamera", "black screen", "schwarzes bild", "not detected", "teams", "zoom"],
        "body": "Check Device Manager for camera under 'Cameras' or 'Imaging devices'. Update driver. Check Windows Privacy → Camera → allow apps. If still black in Teams/Zoom but visible in Camera app, re-install the conferencing app.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-034",
        "category": "hardware",
        "title": "Keyboard or mouse unresponsive",
        "tags": ["keyboard", "tastatur", "mouse", "maus", "unresponsive", "reagiert nicht", "usb", "bluetooth", "wireless"],
        "body": "For USB: try a different port. For Bluetooth: remove and re-pair the device. Check battery for wireless devices. If a wired keyboard fails on multiple ports, raise a ticket for hardware replacement.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    # ------------------------------------------------------------------
    # access (5)
    # ------------------------------------------------------------------
    {
        "id": "kb-040",
        "category": "access",
        "title": "Network drive / shared folder access denied",
        "tags": ["laufwerk", "drive", "shared folder", "freigabe", "access denied", "zugriff verweigert", "permission", "berechtigung"],
        "body": "Access to shared drives requires approval from the drive owner (see CMDB). Submit an access request via https://internal/access-requests. IT will provision access within 1 business day after owner approval.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    {
        "id": "kb-041",
        "category": "access",
        "title": "Application access request",
        "tags": ["application", "app", "anwendung", "access", "zugriff", "permission", "berechtigung", "software", "role"],
        "body": "Application access requires manager approval. Submit a request via the IT portal at https://internal/access-requests, select the application, and add your manager as approver. Provisioning takes up to 2 business days.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    {
        "id": "kb-042",
        "category": "access",
        "title": "SharePoint site or document library access",
        "tags": ["sharepoint", "teams", "onedrive", "site", "library", "access", "zugriff", "permission", "berechtigung", "microsoft 365"],
        "body": "SharePoint access is managed by the site owner. Contact the site owner directly or submit an access request via the site's 'Request access' button. IT can only intervene if the site owner is unavailable.",
        "solution_type": "self_service",
        "priority_hint": "P4",
    },
    {
        "id": "kb-043",
        "category": "access",
        "title": "VPN group or remote access profile missing",
        "tags": ["vpn", "group", "gruppe", "profile", "profil", "remote access", "fernzugriff", "access", "zugriff"],
        "body": "VPN group membership is tied to your AD group. Submit an access request via https://internal/access-requests. Requires manager approval. Provisioning is automated and takes ~15 minutes after approval.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    {
        "id": "kb-044",
        "category": "access",
        "title": "Local admin rights request",
        "tags": ["admin", "administrator", "local admin", "lokaler admin", "elevated", "rights", "rechte", "uac", "privilege"],
        "body": "Local admin rights require CISO approval in addition to manager approval. Submit via https://internal/access-requests with a business justification. Approval process takes 2–3 business days. Temporary admin access (8 h) is available for urgent cases.",
        "solution_type": "it_specialist",
        "priority_hint": "P3",
    },
    # ------------------------------------------------------------------
    # security (2) — always escalate
    # ------------------------------------------------------------------
    {
        "id": "kb-050",
        "category": "security",
        "title": "Phishing email received",
        "tags": ["phishing", "email", "mail", "suspicious", "verdächtig", "link", "attachment", "anhang", "social engineering"],
        "body": "Do NOT click links or open attachments. Forward the email as attachment to security@company.com. Delete from inbox. If you already clicked a link, immediately disconnect from the network and raise a P1 security incident.",
        "solution_type": "escalate_always",
        "priority_hint": "P2",
    },
    {
        "id": "kb-051",
        "category": "security",
        "title": "Suspicious login or account compromise suspected",
        "tags": ["suspicious", "verdächtig", "login", "compromise", "kompromittiert", "breach", "unauthorized", "unberechtigt", "account"],
        "body": "Do NOT log out — preserve session for forensics. Immediately raise a P1 security incident. Security team will lock the account, collect logs, and begin incident response. Do not change the password until Security instructs you to.",
        "solution_type": "escalate_always",
        "priority_hint": "P1",
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
