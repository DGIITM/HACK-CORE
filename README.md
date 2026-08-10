# KrishiSathi

Voice/WhatsApp advisory tool for Punjab wheat farmers — see `CLAUDE.md` for
the full brief, hard constraints, and data contract.

## Quick start (recommended)

```
python setup_and_run.py
```

Or double-click **`run.bat`** (Windows) / run **`./run.sh`** (Mac/Linux).

This one command: creates a `.venv` if you don't have one, installs
dependencies into it, creates `.env` from `.env.example` if you don't have
one, starts the server, and opens the chat UI in your browser. Safe to
re-run any time — it reuses what's already set up.

**Needs Python 3.10–3.13** on your PATH somewhere (`py`, `python3`, or
`python`). Not 3.14+ — `pydantic-core` has no prebuilt wheel there yet and
fails to compile. The script looks for 3.13 first, then 3.12/3.11/3.10.

The app works immediately with an empty `.env` — every module (Gemini
reasoning, weather, translation, TTS, etc.) has a real, honestly-labeled
fallback for when credentials aren't configured; nothing is faked or
silently broken. Add a free Gemini Developer API key to `.env` any time
for real Gemini calls — see `.env.example` for where, and
https://aistudio.google.com/apikey to get one. (The free tier caps at 20
requests/day — plenty for a demo, not for hammering the test suite: the
automated tests never touch the real key regardless, see
`tests/conftest.py`.)

## Manual setup (if you'd rather not use the script)

```
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
python run.py
```

Then open http://localhost:8000.

## Current status

Every module (M1–M9) runs real logic — Gemini (Developer API primary,
Vertex AI fallback), Qdrant retrieval, Open-Meteo weather, Cloud
Translation/TTS/STT, a real difference-in-differences causal model — with
a real, working, honestly-labeled fallback wherever live credentials
aren't configured. Nothing is a stub anymore; `grep -rn "STUB" app/` finds
only a couple of deliberately out-of-scope items (e.g. Firebase Storage
upload for photos, BigQuery migration for M2's data), each documented in
place.

## Layout

```
app/
  main.py          # M10 — wires every router together
  core/
    config.py      # env vars (pydantic-settings)
    dependencies.py
  schemas/         # one file per module — the data-contract shapes
  services/        # one file per module — the real logic lives here
  routes/          # one file per module — thin, calls into services/
frontend/
  index.html       # landing page + chat UI + retailer view (Vue 3 + Bootstrap 5, CDN only)
data/              # M2's datasets (JSON) + runtime SQLite caches (gitignored)
tests/             # one file per module, plus adversarial/regression suites
setup_and_run.py   # one-command local setup + launch (see Quick start above)
```

Note: the project's decided datastore is Firestore (see CLAUDE.md) with a
real local SQLite fallback when Firestore isn't configured — not
SQL/SQLAlchemy, so there's no `models/` or a general `database.py`.

## Endpoints

| Route | Module |
|---|---|
| `POST /entry-point` | M1 Entry Point |
| `POST /risk-context` | M3 Risk Intelligence |
| `POST /recommend` | M4 Recommendation Engine |
| `POST /deliver` | M5 Response Delivery |
| `GET /retailer?district=...` | M6 Retailer Console |
| `POST /log-outcome` | M7 Application & Logging |
| `POST /measure-impact` | M8 Impact Measurement |

M2 (Data Foundation) and M9 (Feedback Loop) have no route — they're read
internally by the other services (`app/services/data_foundation.py`,
`app/services/feedback_loop.py`).

## Tests

```
pytest
```

The automated suite always exercises the deterministic fallback paths —
`tests/conftest.py` clears any local Gemini credentials for the duration
of the test run, so `pytest` never depends on network access or a live
API quota. Run individual modules' live-Gemini paths with ad-hoc scripts
instead (import the service and call it directly) when you want to verify
the real API, not the fallback.
