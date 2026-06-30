# TODO

> Status-Legende: `❌ Offen` · `🔄 In Arbeit` · `✅ Fertig`

## Kritisch

| Status | Task |
|---|---|
| ✅ Fertig | `agent/coordinator.py` — Coordinator-Agent implementiert (Claude API): Klassifikation P1–P4, Kategorie, Konfidenz, Enrichment, Validation-Retry-Loop (max 3), strukturiertes Logging |
| ✅ Fertig | `agent/specialists/password_reset.py` — PasswordResetSpecialist als SDK-Task-Subagent implementiert |
| ✅ Fertig | `agent/specialists/it_specialist.py` — ITSpecialistAgent als SDK-Task-Subagent implementiert |
| ✅ Fertig | `agent/main.py` — Entry-Point mit `stop_reason`-Handling (tool_use / end_turn / max_tokens) |

## Hoch

| Status | Task |
|---|---|
| ✅ Fertig | PreToolUse-Hook aus `agent/hooks.py` in den SDK-Agent-Loop verdrahtet (Coordinator + beide Spezialisten) |
| ✅ Fertig | Escalation-Rules im Coordinator umgesetzt: Konfidenz < 0.75, VIP, Legal-Keywords, Breach-Keywords, Impact > €10k, Non-DE/EN |

## Mittel

| Status | Task |
|---|---|
| ✅ Fertig | `tests/test_tools.py` — 52 Tests für alle 6 Custom Tools + Hooks (Happy Path, Error Path, Edge Cases) |
| ✅ Fertig | Eval-Harness mit erweiterten Metriken: Precision/Recall per Category, Escalation Rate, Adversarial-Pass Rate, False-Confidence Rate |
| ✅ Fertig | Eval-Datasets erweitert: 15 normale Cases + 10 adversariale Cases |

## Niedrig

| Status | Task |
|---|---|
| ✅ Fertig | `ruff check .` — Linting sauber |
| ❌ Offen | `mypy --strict .` — Typ-Checking (mypy nicht installiert) |
