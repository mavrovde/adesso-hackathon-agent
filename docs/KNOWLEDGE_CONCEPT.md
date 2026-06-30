# Knowledge Lookup — Konzept

**Version:** 1.1 (angepasst an Implementierung)
**Datum:** 2026-06-30
**Autor:** Marcel Cossijns
**Zweck:** Konzeptdokument für das Knowledge-Lookup-Tool des IT-Helpdesk-Triage-Agenten

---

## 1. Rolle im Agenten-System

Der Knowledge Lookup ist das **Lesewerkzeug** des IT-Specialist-Agenten und des Coordinators. Er beantwortet: *"Gibt es für dieses Problem eine bekannte Lösung, einen Standard-Prozess, oder ein bekanntes Risiko?"*

```
Inbound Request
      │
      ▼
Coordinator: classify(request) → category
      │
      ▼
Coordinator: lookup_kb(query, category=category)   ◄── dieses Tool
      │
      ├─ solution_type == "self_service"  → Self-Service-Schritte zurückgeben
      ├─ solution_type == "it_specialist" → route mit KB-Kontext im Task-Prompt
      └─ kein Treffer / "escalate_always" → eskalieren
```

---

## 2. Wissensdatenbank — Struktur

Die Wissensdatenbank lebt als **Python-Liste** in `agent/tools/mock_store.py` (`KB_ARTICLES`). Sie wird beim Modulimport in-memory geladen — kein Datenbankserver, kein Netzwerk-Call, offline-fähig.

### 2.1 Schema eines Eintrags

```python
{
    "id": "kb-001",
    "category": "password_reset",       # Coordinator-Kategorie (Filter-Feld)
    "title": "Password reset — Active Directory",
    "tags": ["password", "ad", "reset", "passwort"],  # DE + EN
    "body": "Schritt-für-Schritt-Lösung oder Eskalationshinweis.",
    "solution_type": "self_service",    # self_service | it_specialist | escalate_always
    "priority_hint": "P4",              # P1 | P2 | P3 | P4
}
```

### 2.2 Felder-Erklärung

| Feld | Typ | Zweck |
|---|---|---|
| `id` | string | Eindeutige KB-Referenz, wird im Reasoning-Log gespeichert |
| `category` | string | Muss mit Coordinator-Kategorien übereinstimmen; ermöglicht gefilterte Suche |
| `title` | string | Kurze Beschreibung; fließt in Titel-Scoring ein |
| `tags` | string[] | Primärer Match-Mechanismus; Deutsch UND Englisch |
| `body` | string | Lösungsschritte oder Eskalationshinweis — geht direkt in den Task-Prompt |
| `solution_type` | enum | Steuert, was der Agent nach dem Treffer tut |
| `priority_hint` | enum | Empfohlene Priorität — Coordinator kann überschreiben |

### 2.3 `solution_type` — Bedeutung

| Wert | Bedeutung | Agent-Verhalten |
|---|---|---|
| `self_service` | Nutzer kann selbst lösen | KB-Body als Antwort zurückgeben, Ticket schließen |
| `it_specialist` | Braucht IT-Eingriff | Route an IncidentSpecialist mit KB-Body als Kontext |
| `escalate_always` | Immer eskalieren | Ticket anlegen, sofort eskalieren, kein Auto-Action |

### 2.4 Kategorien-Mapping

```
Coordinator-Kategorie    Typische subcategory-Keywords in Tags
─────────────────────    ──────────────────────────────────────────────────
password_reset           password, passwort, ad, sso, mfa, reset, locked
network                  vpn, wifi, wlan, proxy, dns, firewall, rdp, lan
software                 office, crash, lizenz, outlook, teams, update, virus
hardware                 docking, monitor, drucker, printer, kamera, tastatur
access                   laufwerk, sharepoint, permission, admin, gruppe
security                 phishing, breach, ransomware, suspicious, verdächtig
```

---

## 3. Such-Mechanismus

### 3.1 Algorithmus (implementiert in `agent/tools/lookup_kb.py`)

```
query + optionale category
      │
      ▼
1. Category-Filter: Wenn category angegeben → nur Einträge dieser Kategorie
      │
      ▼
2. Tokenisierung: query.lower().split()
      │
      ▼
3. Tag-Hits:   len(query_tokens ∩ entry.tags)
   Titel-Hits: Anzahl query_tokens die in entry.title.lower() vorkommen
      │
      ▼
4. Score = tag_hits + title_hits
      │
      ▼
5. Sortierung DESC, cutoff bei score == 0, top 3 zurückgeben
```

**Bewusst einfach gehalten:** Kein Embedding, kein Levenshtein, kein TF-IDF.
Tags decken Deutsch UND Englisch ab (`"passwort"` + `"password"`) — das ist die primäre Internationalisierungsstrategie für den MVP.

### 3.2 Was der Agent mit dem Ergebnis macht

```python
# Aus dem Coordinator / Specialist-Prompt heraus:
result = lookup_kb("VPN trennt sich", category="network")

if not result["data"]["articles"]:
    # Kein Treffer → eskalieren
    ...
else:
    article = result["data"]["articles"][0]
    if article["solution_type"] == "self_service":
        # Self-Service-Body als Antwort zurückgeben
        ...
    elif article["solution_type"] == "it_specialist":
        # KB-Body in Specialist-Task-Prompt einfügen
        ...
    elif article["solution_type"] == "escalate_always":
        # Immer eskalieren, kein Auto-Action
        ...
```

---

## 4. Tool-Interface

### 4.1 Tool-Beschreibung (wie der Agent es sieht)

```
Name: lookup_kb

Sucht die interne IT-Wissensdatenbank nach bekannten Lösungen und
Standard-Prozessen für IT-Helpdesk-Anfragen.

Wann benutzen:
  - Bevor eine Anfrage geroutet wird, um Self-Service-Lösungen zu prüfen
  - Um Kontext für den Specialist-Agent anzureichern

Was dieses Tool NICHT tut:
  - Es liest keine Live-Systemdaten (kein ITSM, kein AD)
  - Es enthält keine benutzerspezifischen Daten
  - Kein Treffer (leere articles-Liste) ist kein Fehler — bedeutet: eskalieren

Eingabe:
  - query:    Freitext der Anfrage (Original oder zusammengefasst)
  - category: Erkannte Kategorie (optional, verbessert Präzision)
```

### 4.2 Input

```python
def lookup_kb(query: str, category: str | None = None) -> dict:
```

### 4.3 Output (Erfolg)

```python
{
    "ok": True,
    "data": {
        "articles": [
            {
                "id": "kb-002",
                "title": "VPN connectivity issues",
                "body": "Restart the VPN client...",
                "solution_type": "self_service",
                "priority_hint": "P4",
            }
        ]
    }
}
```

Leere `articles`-Liste ist kein Fehler — bedeutet für den Agent: eskalieren.

### 4.4 Fehler-Codes

| Code | Ursache |
|---|---|
| *(kein Fehlerfall)* | Kein Treffer → `articles: []`, `ok: True` |

Das Tool wirft keine Fehler bei ausbleibendem Treffer — konsistent mit dem Projekt-Muster: nur systeminterne Fehler (z. B. `USER_NOT_FOUND`) sind `isError: true`.

---

## 5. Wissensdatenbank — Initialbestand (~30 Einträge)

| Kategorie | Anzahl | solution_type |
|---|---|---|
| `password_reset` | 5 | überwiegend `self_service` |
| `network` | 7 | Mix `self_service` / `it_specialist` |
| `software` | 6 | Mix `self_service` / `it_specialist` |
| `hardware` | 5 | Mix `self_service` / `it_specialist` |
| `access` | 5 | überwiegend `it_specialist` |
| `security` | 2 | `escalate_always` |

Einträge leben in `agent/tools/mock_store.py` → `KB_ARTICLES`.

---

## 6. Dateistruktur

```
agent/tools/
  mock_store.py      # KB_ARTICLES + USERS + TICKETS
  lookup_kb.py       # Tool-Implementierung

docs/
  KNOWLEDGE_CONCEPT.md   # dieses Dokument
```

---

## 7. Erweiterungspfad (post-Hackathon)

| Stufe | Was | Warum |
|---|---|---|
| **MVP** | Python-Liste + Tag-Match | Hackathon-Demo, kein Overhead |
| **Stufe 1** | SQLite + FTS5 | Bessere Suche, serverless |
| **Stufe 2** | Embeddings + ChromaDB | Semantische Suche |
| **Stufe 3** | ITSM-Tickethistorie als KB-Quelle | KB lernt aus echten Tickets |
