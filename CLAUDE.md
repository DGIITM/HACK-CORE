# KrishiSathi — HACK CORE 2026

Read this before any work in this repo. It is the source of truth for what we're building and the decisions already made. Don't re-derive these.

---

## What we're building

**KrishiSathi** — a voice/WhatsApp advisory tool for Punjab wheat farmers, in Hindi, Punjabi, and English.

A farmer describes a crop problem by voice (or text, or photo). The system checks field-level risk — weather, soil, regional pest history — decides whether now is even the right time to act, then recommends a specific biological product with a confidence score and a plain-language reason. Later, the farmer or a field agent logs what happened. At season end, a causal model estimates how much of the yield change was actually caused by the product, reported in rupees per acre. That estimate feeds back to sharpen future recommendations.

**The demo we're building toward:** one farmer, one field, one season, traced start to finish.

## The problem (use this framing in any docs or copy)

Biological products work, but farmers can't verify that before buying, companies can't prove it after selling, and the retailer standing between them has no evidence to offer either. It's a trust gap, not a technology gap.

## Deadline

**5:00 PM, 16 August 2026.** Deliverables: concept note (.doc/.pdf), pitch deck (.ppt), this GitHub repo, and a 3-minute video.

This is the *ideation phase* submission — a qualifying round. The top 3 teams go to a 36-hour build sprint at IIT Ropar on 9–11 September. So this repo needs to show real, working progress, not a finished product.

---

## Hard constraints — do not violate

1. **The recommendation engine must never invent a product.** Retrieval returns candidates; the model may only recommend from those candidates. If nothing fits well, say so honestly rather than forcing a recommendation. This is the single highest-risk line in the codebase — test it adversarially.
2. **Never overclaim precision in the causal estimate.** Report ranges, not single confident numbers. Overclaiming loses credibility with the agronomist judge faster than anything else.
3. **Label simulated data as simulated.** We use synthetic/placeholder data in several places. That's explicitly allowed by the brief. Quietly implying it's real is not.
4. **Farmer-facing text must be jargon-free.** No agricultural terminology, no chemical names in explanations. Write for someone with no agricultural training.
5. **Don't build a marketplace, delivery, or credit features.** Out of scope, dilutes the pitch.

---

## Tech stack — decided, don't re-litigate

| Layer | Choice | Notes |
|---|---|---|
| Backend | FastAPI | One shared service, one endpoint per module |
| Hosting | Cloud Run | |
| LLM | `gemini-2.0-flash-001` via Vertex AI | Stable GA multimodal model. Handles text + image in one call. Avoid preview models — they change under you mid-build. |
| Speech-to-Text | Google Cloud STT | Language codes: `hi-IN`, **`pa-guru-IN`** (Gurmukhi — NOT `pa-IN`, that fails silently), `en-IN` |
| Text-to-Speech | Google Cloud TTS, Chirp 3 HD voices | Punjabi HD voice is in Preview — test early |
| Translation | Google Cloud Translation API | |
| Vector DB | Qdrant | For efficacy dataset retrieval |
| Database | Firestore | Offline persistence enabled (`persistentLocalCache`) |
| File storage | Firebase Storage | Crop photos |
| Data warehouse | BigQuery | Pest history, efficacy tables |
| Causal model | Python + `statsmodels` | Difference-in-differences. Do NOT reach for DoWhy/EconML — too much setup for the timeline. |
| WhatsApp | Twilio Sandbox or styled web chat | Real Business API approval takes weeks — not viable |

**Request size limit:** keep Gemini requests under 20 MB. Compress photos before sending.

---

## Module structure

Ten modules. Each is independently buildable and testable against stub data from its dependencies.

| ID | Module | Job |
|---|---|---|
| M1 | Entry Point | Voice/text/photo input → structured request |
| M2 | Data Foundation | Datasets everything else reads from |
| M3 | Risk Intelligence | Weather, soil, pest → readiness score |
| M4 | **Recommendation Engine** | Retrieval + constrained reasoning → product + confidence + reason |
| M5 | Response Delivery | Translate, speak, set expectations, chat UI |
| M6 | Retailer Console | District view of recommendations + evidence |
| M7 | Application & Logging | Batch check, outcome logging, offline sync |
| M8 | **Impact Measurement** | Causal attribution → ROI in ₹/acre |
| M9 | Feedback Loop | Outcomes sharpen future recommendations |
| M10 | Platform & Infra | API, hosting, shared contract |

**M4 and M8 are the depth pieces** — they carry the differentiation. Budget the most time and care here.

**M2 should be built first** — nearly everything reads from it.

### Dependencies

```
M1 → M3 (reads M2)
M1 → M4 (reads M2)
     M4 → M5
     M4 → M6 (parallel)
M1 → M7 (reads M2)
     M7 → M8 → M9 ↺ back into M4 and M6
M10 underneath everything
```

---

## The data contract

Every module talks through these shapes. **Agree any change with the whole team before altering these** — the parallel build depends on them being stable.

### Farmer request (M1 output)
```json
{
  "crop": "wheat",
  "location": { "district": "Ludhiana", "state": "Punjab" },
  "symptom_description": "leaves turning yellow at the tips",
  "language": "pa",
  "photo_present": true,
  "photo_url": "gs://..."
}
```

### Risk context (M3 output)
```json
{
  "readiness_score": 3,
  "should_proceed": true,
  "weather_summary": "no heavy rain expected for 5 days",
  "active_pests": ["yellow rust"],
  "early_warning": null
}
```

### Recommendation (M4 output)
```json
{
  "recommended_product": "...",
  "confidence_score": 0.78,
  "plain_language_reason": "...",
  "mode_of_action": "...",
  "neighbour_proof": {
    "farmers_nearby": 14,
    "avg_outcome": "9% yield improvement",
    "available": true
  },
  "no_confident_match": false
}
```

### Outcome log (M7 output)
```json
{
  "farmer_id": "...",
  "product_used": "...",
  "batch_verified": true,
  "application_date": "2026-03-14",
  "observed_outcome": "...",
  "yield_result": 42.5,
  "synced": true
}
```

### Impact estimate (M8 output)
```json
{
  "estimated_effect_pct": 12.0,
  "confidence_range": [8.0, 15.0],
  "roi_per_acre_inr": 4200,
  "nitrogen_saved_kg": 18,
  "data_basis": "simulated"
}
```

---

## Build order

1. Lock the contract above (done — it's in this file)
2. Landing page + chat UI shell, built against **fake JSON** matching these shapes
3. M2, M3 in parallel — testable by script, no UI needed
4. M4, M8 in parallel — the depth pieces, start early
5. Integration day — swap fake JSON for real API calls
6. Break-testing: Punjabi voice, offline sync, adversarial prompts against M4
7. Video, concept note, deck

**Do not build the UI first and the backend after.** They go in parallel, connected by the stub contract. The hardest work (M4, M8) must not be left for last.

---

## What's real vs. simulated

**Real / live:** voice input, translation, retrieval, offline logging, readiness score, causal model *code*

**Simulated but honestly labeled:** IoT soil sensors, satellite processing, WhatsApp Business API, causal model *input data* (synthetic season data with a known ground-truth effect), counterfeit batch registry

**Deferred to phase 2 — designed, not built:** public efficacy benchmark platform, distributor demand forecasting, trained plant-stress vision model, SMS/IVR fallback, online retraining

---

## Trust features — these are the differentiators, don't drop them under time pressure

These came out of market research and each targets a documented reason biologicals fail to get adopted. They're cheap to build (mostly output formatting) and they're what separates us from teams building a generic advisory chatbot.

- **Mode-of-action explanation** — say *why* it works, in plain words. Unclear mode of action is a named trust barrier.
- **Expectation setting** — "you won't see change for ~3 weeks." Biological benefits are delayed and subtle; farmers abandon products when nothing visibly happens. This is the #1 abandonment cause.
- **Neighbour proof** — "14 farmers within 20km used this." Social proof is what actually drives adoption in this market.
- **Retailer console** — closes the grower/retailer disconnect the brief explicitly names. Most competing teams will build farmer-only.
- **Counterfeit check** — ~25% of India's agrochemical market is non-genuine. A fake product failing would otherwise be recorded by M8 as a genuine product failing, corrupting our data.

---

## Conventions

- Keep farmer-facing strings in a separate file, not hardcoded — they need translating
- Every module gets a stub/mock mode so others can build against it before it's real
- Commit messages: `M4: add retrieval constraint` — prefix with the module ID
- Don't commit API keys. Use environment variables.

---

## Mentors

ANNAM.AI: Dr. Shahbaz Khanday · Syngenta: Pradeep Kethireddy
Always CC `hackathon@annam.ai` on mentor correspondence.
Resolve internally first; escalate only what genuinely needs expert input.
