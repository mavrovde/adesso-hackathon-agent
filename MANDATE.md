# The Mandate — IT Helpdesk Triage Agent

**Version:** 1.0  
**Date:** 2026-06-30  
**Owner:** Marcel Cossijns, adesso SE  
**Audience:** Legal, Compliance, Management  
**Status:** Draft for review

---

## 1. Purpose

This document defines the authority, boundaries, and accountability model of the IT Helpdesk Triage Agent ("the Agent"). It establishes what the Agent may decide autonomously, what it must escalate to a human, and what it is categorically prohibited from doing. This Mandate is the binding reference for Legal, Compliance, and any future audit.

---

## 2. Scope

| Dimension | In Scope | Out of Scope |
|---|---|---|
| **Input channel** | Web form with SSO authentication | E-mail, Slack, phone, walk-in |
| **Users** | All employees accessing the verified web portal | External contractors without SSO, anonymous submissions |
| **Systems written** | ITSM ticket queue, password reset service | HR systems, payroll, financial systems, ERP |
| **Languages** | German, English | All other languages (escalate) |

---

## 3. What the Agent Decides Alone

The Agent acts autonomously **only** when all of the following are true:

1. The request arrives via the SSO-authenticated web form.
2. Confidence in classification is **≥ 0.75**.
3. The request category is not in the escalation list (Section 4).
4. No high-risk pattern is detected by the hard-block hooks (Section 6).

| Decision | Condition | Action |
|---|---|---|
| Classify request | All requests | Assign category + priority level |
| Route to team queue | Confidence ≥ 0.75 | Write to ITSM ticket system |
| **Auto-resolve: password reset** | Account is active AND not security-flagged AND request is via verified SSO channel | Execute reset via password reset service |
| Block adversarial input | Prompt injection detected | Hard block, log, create security incident |

**Password reset auto-resolution requires all conditions to be met simultaneously. Failure of any single condition routes to a human.**

---

## 4. What the Agent Escalates

Escalation means the Agent creates a ticket, attaches its reasoning log, and halts — a human takes all further action.

| Trigger | Rule |
|---|---|
| Low confidence | Classification confidence < 0.75 |
| Ambiguous request | Agent sends automated clarification request to the requester before escalating; if unresolved, escalates to 1st-Level Helpdesk |
| VIP user | User role is C-Level / Board / Supervisory Board **or** user is on the static VIP whitelist |
| Legal / compliance mention | Request body contains legal, compliance, audit, GDPR, Datenschutz, lawsuit, or equivalent terms |
| High dollar impact | Estimated business impact > €10,000 (derived from system or stated by requester) |
| Category: `vip_escalation` | Always, no exceptions |
| Category: `unknown` | Always |
| Unclassifiable language | Request not in German or English |

---

## 5. What the Agent Must Never Touch

These are hard prohibitions. No business justification, no override flag, no confidence level unlocks these actions. They are enforced by a deterministic `PreToolUse` hook that fires **before** any model decision.

| Prohibition | Rationale |
|---|---|
| **Lock, suspend, or delete a user account** | Irreversible action with potential legal and operational impact; requires human authorization |
| **Transmit, log, or route PII beyond the ITSM system** | GDPR compliance; PII is confined to the authenticated ITSM context |
| **Act on a security-flagged or frozen account** | Any write action on a compromised account is a hard stop |
| **Route to a known-bad or unverified external endpoint** | Prevents exfiltration and supply-chain risk |
| **Execute any action on a VIP account without human approval** | VIP actions are always human-authorized |
| **Override a prior human decision** | The Agent never reverses what a human has approved or denied |

---

## 6. What We Are Deliberately Not Automating

This section is the explicit boundary for Legal. These decisions remain with humans by design, not by technical limitation.

- **Final denial of any request.** The Agent may flag, route, and escalate — it does not deny. Denial carries legal and reputational risk that requires human accountability.
- **Any action affecting more than one user account.** Bulk operations are out of scope.
- **Requests involving employment, HR, or personal data changes.** These cross into HR and labor law territory.
- **Security incident response beyond initial detection.** Detecting an injection attempt is in scope; containment, forensics, and communication are not.
- **Decisions during a declared IT security incident.** If an incident is active, all automated routing is suspended.
- **Any decision the Agent has already retried 3 times without success.** Persistent failure escalates unconditionally.
- **Onboarding and offboarding workflows.** Account creation and termination are human-authorized by policy.

---

## 7. Accountability and Auditability

- Every routing decision produces a structured log entry containing: `category`, `confidence`, `routing_target`, `reasoning`, `requires_human`, `retry_count`, `timestamp`, `request_id`.
- Logs are immutable and retained for a minimum of 12 months (GDPR-compliant: no PII in the reasoning log).
- The Agent's decisions are replayable from the log alone — no black-box outcomes.
- Human overrides are recorded with the overriding user's identity and a mandatory reason field.

---

## 8. Escalation Hierarchy

```
Agent → 1st-Level Helpdesk → IT Specialist → Security/Legal (if flagged)
```

VIP escalations bypass 1st-Level and go directly to IT Management.

---

## 9. Open Questions (for Legal review)

1. Is the 0.75 confidence threshold acceptable as the autonomous-action bar, or does Legal require a higher threshold for specific categories?
2. Does the VIP whitelist require a formal approval process for additions/removals?
3. Is automated PW-reset (without human in the loop) acceptable given SSO verification, or does Legal require a second factor?
4. What is the retention period for the structured reasoning logs under current GDPR policy?

---

*This document does not constitute legal advice. It is a product scope definition subject to Legal and Compliance review before the Agent is deployed in a production environment.*
