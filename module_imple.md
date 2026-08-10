# KrishiSathi — Remaining Modules: M3, M9, M6

Paste this whole document into Claude Code. Read CLAUDE.md first, as always.
This covers all three remaining modules in sequence — complete and merge
each one fully before starting the next. The order below is deliberate,
not arbitrary: M3 has no dependency on the other two, M9 needs M7/M8
(both already real), and M6 is last because it becomes more useful once
M9's evidence function exists.

---

## HOUSEKEEPING — do this first, before anything else

Check `git log --oneline main`. If M5 (Response Delivery) is not yet
merged, merge it now using the standard sequence before starting any new
module:

```
git checkout module/m5-response-delivery
git diff main --stat
git checkout main
git pull
git merge module/m5-response-delivery
git push
git branch -d module/m5-response-delivery
```

If M5 is already merged, skip this and proceed.

---

## AUTONOMOUS MERGE AUTHORIZATION

For each module below, once you've completed the build and it clears
every item in that module's "Definition of done" checklist, merge it
into `main` yourself using the same sequence used for every prior
module (log check → diff --stat → checkout main → pull → merge → push
→ delete branch). Do not wait for a human to say "merge it."

**Exception:** if a test genuinely fails and you can't resolve it, or a
design decision below is ambiguous and you have to guess at intent in a
way that could be wrong, STOP. Leave the branch unmerged, write a clear
note explaining exactly what's blocking and what you'd need to know to
proceed, and move on to documenting it rather than guessing silently.

At the very end, after all three modules are handled, write one summary
covering all three — same format as every module report so far: what
was built, how it was verified, anything flagged honestly, what's
merged vs. left for review.

---

## MODULE 1 OF 3 — M3: Risk Intelligence

**Branch:** `module/m3-risk-intelligence`, off latest `main`.

### What this module does

Before M4 recommends anything, check whether now is even a reasonable
time to act — weather risk, soil condition, and active regional pests.
This replaces the stub in `risk_context.py`.

### Exact output contract (from CLAUDE.md — do not deviate)

```json
{
  "readiness_score": 3,
  "should_proceed": true,
  "weather_summary": "no heavy rain expected for 5 days",
  "active_pests": ["yellow rust"],
  "early_warning": null
}
```

### What to build

1. **Weather integration.** No paid weather API has been set up anywhere
   in this project. Use a free, no-API-key-required service — Open-Meteo
   is a reasonable default (forecast endpoint, no auth needed). If it's
   unreachable, fall back to a clearly-labeled neutral/default weather
   assumption rather than crashing or fabricating a forecast — same
   fallback honesty pattern as every other module so far.

2. **Pest lookup.** Call M2's `get_pest_history(district, crop)`, filter
   to pests whose `typical_month` matches the current month (or is
   within a reasonable window — your judgment on window size, document
   it).

3. **Soil lookup.** Call M2's `get_soil_type(district)`.

4. **Readiness score — a rules-based function, NOT a trained model, per
   CLAUDE.md.** Something in this shape (adjust weights as makes sense,
   but keep it simple and explainable in one sentence):
   ```
   score = 0
   if forecast_rain_next_3_days > threshold: score -= 2
   if soil_moisture_reasonable: score += 1
   if active_pest_for_this_crop_this_month: score += 2
   should_proceed = score >= 0
   ```
   If `should_proceed` is false, populate `early_warning` with a short,
   plain-language, farmer-facing sentence (use whichever Gemini client
   M1/M4/M5 currently use for this — do not set up a second, different
   auth pattern). If true, `early_warning` must be `null`.

5. **Unknown district handling.** If a district isn't in M2's tables,
   return a clearly labeled neutral/default response — do not fabricate
   confident-looking data for a place you have no data on.

6. **Wire into the real flow.** Check how M4 currently gets called from
   the frontend/entry-point sequence. Per CLAUDE.md's dependency graph
   (M1 → M3 → M4), M3's output should feed into M4 before a
   recommendation is generated. Make the minimal change needed to wire
   this — do not restructure M4 beyond what's needed to consume real
   risk context instead of nothing/a stub. If M4 already expects this
   shape, this may just mean removing a stubbed call and pointing it at
   the real M3 function.

### Testing requirements

- Unit tests for the readiness-score logic across a range of synthetic
  weather/soil/pest combinations — deterministic, no external API
  needed for these.
- A test for the unknown-district case.
- A test for weather-API-unreachable fallback behavior.
- After wiring into M4: re-run M4's existing full test suite (including
  the 20 adversarial tests) to confirm zero regression.

### Definition of done

- [ ] All new tests pass, plus M4's full existing suite still passes
- [ ] `/risk-context` returns the exact contract shape above
- [ ] Unknown district and weather-API-down cases handled honestly, not
      fabricated
- [ ] `/recommend` genuinely consumes real M3 output, verified via curl
      with at least one district that has an active pest match and one
      that doesn't
- [ ] No stray `# STUB:` comments left in this module's files

---

## MODULE 2 OF 3 — M9: Feedback Loop

**Branch:** `module/m9-feedback-loop`, off latest `main` (after M3 is
merged).

### What this module does

Makes every measured outcome sharpen future recommendations. This is
what turns four real modules into an actual loop, per CLAUDE.md: "a
simple running average... does not need to be a retraining pipeline —
arithmetic is enough."

### What to build

1. **Check what M8 currently persists.** M8 computes impact estimates
   on demand against synthetic data — check whether it currently saves
   any per-request result anywhere. If it doesn't persist results keyed
   by product/region, add a minimal persistence step (store the last N
   computed estimates, keyed by product_name and district) — small
   addition, not a rewrite of M8's logic.

2. **Running average function**, reading from M7's `get_outcomes(product_name)`
   (already built specifically for this) and the M8 persistence from
   step 1:
   ```
   get_confidence_boost(product_name, district) -> float
   ```
   Compute a small, capped adjustment based on real logged positive
   outcomes — e.g. a small increment per positive outcome, capped at a
   sensible maximum so it can never dominate the base confidence score.
   **If there's no outcome data yet for a product/region, the boost
   must be exactly zero — not fabricated, not a guess.** Same honesty
   pattern as `no_confident_match` in M4.

3. **Wire into M4.** M4's `confidence_score` calculation should call
   this and add the boost. This must be a minimal, additive change to
   `recommend.py` — do not rewrite the scoring logic. Re-run M4's full
   test suite afterward, specifically confirming the 20 adversarial
   tests still pass unchanged.

4. **Build (but don't wire yet) the retailer evidence function**, since
   M6 doesn't exist yet:
   ```
   get_retailer_evidence(district) -> dict
   ```
   Summarize recent recommendation/outcome activity for a district in
   whatever shape seems reasonable given M7/M8's data — this becomes
   M6's data source next. Leave it unconsumed by any endpoint for now,
   same pattern M7 used when it built `get_outcomes()` ahead of M8/M9
   needing it.

### Testing requirements

- Unit test the running-average math directly — deterministic, no
  external API.
- **The key test:** confirm M4's confidence score genuinely increases
  when synthetic positive M7 outcomes exist for a product, versus when
  none exist. This is the "does the loop actually work" test — the
  equivalent of M8's recovery-of-known-effect test.
- Confirm the zero-data case produces exactly zero boost, with a test.
- Re-run M4's entire existing suite — zero regression required.

### Definition of done

- [ ] All new tests pass, M4's full existing suite still passes
      unchanged
- [ ] Demonstrated (via test) that logged outcomes measurably change
      M4's confidence score
- [ ] Zero-data case produces zero boost, not a fabricated one
- [ ] `get_retailer_evidence()` exists and returns sensible data, even
      though nothing calls it yet
- [ ] No stray `# STUB:` comments left in this module's files

---

## MODULE 3 OF 3 — M6: Retailer Console

**Branch:** `module/m6-retailer-console`, off latest `main` (after M9 is
merged).

### What this module does

A read-only view for a retailer — what's being recommended in their
district, with evidence, and a simple stock signal. This replaces the
stub in `retailer.py`. Note: `retailer.py` currently uses M2's
`get_product_catalog()` backward-compat adapter — per the note from M4's
build, this is fine to keep using here (the adapter exists specifically
for this module), do not switch it to reading `get_efficacy_dataset()`
directly.

### Output contract (not yet defined in CLAUDE.md's data contract
section — use this shape, and it's fine to adjust field names slightly
if something more natural emerges during the build, just keep it
internally consistent):

```json
{
  "district": "Ludhiana",
  "recent_recommendations": [
    {
      "product_name": "...",
      "count": 5,
      "avg_confidence": 0.74,
      "outcomes_logged": 3,
      "avg_outcome_summary": "9% yield improvement, based on 3 logged outcomes"
    }
  ],
  "stock_signal": [
    { "product_name": "...", "demand_level": "high" }
  ],
  "generated_at": "2026-08-13T10:00:00Z"
}
```

### What to build

1. **Check whether M4 currently persists recommendation history**
   anywhere, or just computes-and-returns per request with nothing
   saved. If nothing is persisted, add a minimal append-only log (district,
   product_name, confidence_score, timestamp) written each time
   `/recommend` returns a result — small addition to `recommend.py`, not
   a restructure.

2. **Aggregate by district and product** from that log: count, average
   confidence.

3. **Pull real evidence** using M9's `get_retailer_evidence(district)`
   function to populate `avg_outcome_summary` and `outcomes_logged`. If
   there's no evidence yet for a district/product, say so honestly
   ("no outcomes logged yet for this product in this area") rather than
   inventing a number.

4. **Stock signal** — a simple heuristic ranking products by recent
   recommendation frequency into `high`/`medium`/`low` demand. This is
   explicitly NOT a forecasting model, per CLAUDE.md — plain
   aggregation only.

5. **New endpoint:** `/retailer?district=...`, replacing the current
   stub.

6. **Minimal frontend.** A simple read-only view is enough — per
   CLAUDE.md, "a table or a few cards is enough — this doesn't need to
   be polished." Reuse the existing Vue + Bootstrap setup already in
   `frontend/index.html`; add a small second section or tab rather than
   a separate app. Don't over-invest time here.

### Testing requirements

- Test the aggregation logic against synthetic recommendation history.
- Test the district-with-no-data case returns an honest, empty-but-well-formed
  response rather than an error or fabricated data.
- Test that `stock_signal` ranking responds correctly to different
  synthetic frequency distributions.

### Definition of done

- [ ] All new tests pass
- [ ] `/retailer?district=...` returns real, honestly-computed data for
      a district with activity, and an honest empty response for one
      without
- [ ] Frontend shows a minimal retailer view, verified by confirming
      the served HTML contains the new markup (same verification
      standard M1 used when a full browser click-test wasn't available)
- [ ] No stray `# STUB:` comments left in this module's files

---

## AFTER ALL THREE

Run the full test suite one final time. Confirm `main` is in a fully
demoable state — start the server, curl every endpoint once, confirm
the frontend loads and a full chat interaction (including the new
retailer view) works.

Write the final summary report: what was built across all three
modules, what got merged automatically versus left for review and why,
and any bugs caught during verification — same honest format as every
report so far. This is the first thing to read on return.