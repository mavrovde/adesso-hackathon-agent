# TODO

> Status-Legende: `❌ Offen` · `🔄 In Arbeit` · `✅ Fertig`

## Kritisch

| Status | Task |
|---|---|
| ✅ Fertig | `agent/coordinator.py` — Coordinator-Agent implementieren (Claude Agent SDK): Klassifikation P1–P4, Kategorie, Konfidenz, Enrichment, Validation-Retry-Loop (max 3), strukturiertes Logging |
| ✅ Fertig | `agent/specialists/password_reset.py` — PasswordResetSpecialist als SDK-Task-Subagent implementieren |
| ✅ Fertig | `agent/specialists/it_specialist.py` — ITSpecialistAgent als SDK-Task-Subagent implementieren |
| ✅ Fertig | `agent/main.py` — Async-Entry-Point mit `stop_reason`-Handling (tool_use / end_turn / max_tokens) |

## Hoch

| Status | Task |
|---|---|
| ✅ Fertig | PreToolUse-Hook aus `agent/hooks.py` in den SDK-Agent-Loop verdrahten |
| ✅ Fertig | Escalation-Rules im Coordinator umsetzen: Konfidenz < 0.75, VIP, Legal-Keywords, Sprache nicht DE/EN, Impact > €10k |

## Mittel

| Status | Task |
|---|---|
| ❌ Offen | `tests/test_tools.py` — alle 6 Custom Tools testen (Happy Path, Error Path, Edge Cases) |
| ✅ Fertig | Eval-Harness vollständig ausführen (setzt Coordinator voraus) und Metriken ergänzen: Precision per Category, Escalation Rate, Adversarial-Pass Rate, False-Confidence Rate |

## Niedrig

| Status | Task |
|---|---|
| ❌ Offen | `ruff check . && ruff format .` — Linting und Formatierung prüfen |
| ❌ Offen | `mypy --strict .` — Typ-Checking prüfen |

