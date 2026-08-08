# KrishiSathi

Voice/WhatsApp advisory tool for Punjab wheat farmers — see `CLAUDE.md` for
the full brief, hard constraints, and data contract.

## Current status: skeleton pass

Every module (M1–M9) exists as a stub wired through the real data-contract
shapes. Nothing calls Gemini, Qdrant, Firestore, BigQuery, or statsmodels
yet — all responses are hardcoded or lightly randomized fake data. Run:

```
grep -rn "STUB" app/
```

to see exactly what real logic is still missing, module by module.

## Run locally

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python run.py
```

Then open http://localhost:8000 — the chat UI calls `/entry-point` then
`/recommend` and displays whatever the stubs return.

## Layout

```
app/
  main.py          # M10 — wires every router together
  core/
    config.py      # env vars (pydantic-settings)
    dependencies.py
  schemas/         # one file per module — the data-contract shapes
  services/        # one file per module — all STUB logic lives here
  routes/          # one file per module — thin, calls into services/
frontend/
  index.html       # landing page + chat UI (Vue 3 + Bootstrap 5, CDN only)
tests/
  test_routes.py   # contract-shape smoke tests for every route
```

Note: the project's decided datastore is Firestore (see CLAUDE.md), not
SQL/SQLAlchemy — so this skeleton pass has no `models/` or `database.py`;
nothing yet persists anything.

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
