# V3 Explanation Experiment — Protocol

> **Written:** 15 Nov 2026, before any V3 explainer code existed and before any V3 explanation value was computed.
> **Status:** fixed. It transcribes the reviewed Stage 1–4 plan (approved 15 Nov 2026). Any later change must be added as a dated amendment at the end, with the reason, and must never be made after seeing SHAP-vs-LIME agreement on V3.
> **Binding to code:** every V3 explanation run records this file's SHA-256 and the git commit in its metadata, and refuses to run unless `results/v3/freeze.json` checks clean.

## 1. What is explained

- **Model:** the frozen V3 stack (XGBoost + LightGBM → Logistic Regression, 348 features), loaded from `artifacts/v3/final_model.joblib`. Never a single base model.
- **Input:** the cleaned URL `url_norm` of a test-set row.
- **Value function v(S):** the stack's probability for class c*, where c* is the class the stack predicts for the full URL. S is a set of kept units. The URL is rebuilt with the units outside S masked, all 348 features are recomputed from the rebuilt string, and the full stack is called. c* stays fixed across all coalitions of that URL. SHAP and LIME call the same function.
- **No re-normalization:** rebuilt strings are featurized exactly as built; `normalize_url` is not applied to them.

This is a **new experiment**, not a V3 replication of the V2 study. The explanation unit changes from 36 engineered features to URL segments, so V3 agreement numbers are not compared with V2's 0.173. The paper says this plainly.

## 2. Units and masking

- **Segment:** each maximal ASCII `[A-Za-z0-9]+` run in `url_norm`. All other characters, including non-ASCII ones, are punctuation and are never masked. (137 of 94,677 test URLs contain non-ASCII characters.)
- **Cap:** at most M = 10 units. A URL with more than 10 segments has its segments merged into 10 contiguous groups with `np.array_split` over segment indices. A group is masked by masking all of its segments; the punctuation between them is kept. n always means the number of units after the cap.
- **Eligibility:** at least 6 raw segments.
- **Primary masking rule (delete):** remove the unit's characters and keep all punctuation. Two segments can never merge, because punctuation separates them.
- **Secondary rule (placeholder, pilot diagnostic only):** replace each masked segment with `x` repeated to the same length.
- **Empty coalition:** v(∅) is the stack's output on the fully masked string. Under deletion this is the URL's punctuation skeleton (e.g. `./?=`), or `""` if there is no punctuation. It must be finite.

**Eligible share by V3 predicted class, whole test set** (segment counting only, no model calls; computed 15 Nov 2026):

| Predicted class | Test URLs | Median segments | Eligible (≥ 6) | Share eligible | Share merged (> 10) |
|---|---:|---:|---:|---:|---:|
| Benign | 64,364 | 7 | 43,460 | 0.6752 | 0.2568 |
| Defacement | 14,292 | 11 | 12,206 | 0.8540 | 0.5563 |
| Malware | 3,359 | 7 | 2,628 | 0.7824 | 0.0938 |
| Phishing | 12,662 | 5 | 4,391 | 0.3468 | 0.0812 |
| All | 94,677 | 7 | 62,685 | 0.6621 | 0.2727 |

Phishing loses about two thirds of its URLs to the eligibility rule. Results therefore describe longer URLs; this is reported as a limitation.

## 3. Explainers

**SHAP — exact Shapley values.** All 2^n coalitions are evaluated (64 to 1,024 model calls). φ_i = Σ_{S ⊆ N\{i}} |S|!(n−|S|−1)!/n! · (v(S ∪ {i}) − v(S)). Written in our own code. Additivity Σφ_i = v(N) − v(∅) is checked on every URL. Independent check: on one pilot URL, the values are compared with `shap.ExactExplainer` (time-boxed to 30 minutes) or, failing that, with a brute-force average of marginal contributions over all n! orderings on a URL with n = 6.

**LIME — the library's own fitter on our masks.** `lime.lime_base.LimeBase.explain_instance_with_data` (lime 0.2.0.1), `feature_selection="none"` so every unit gets a weight. Sampling copies the installed `LimeTextExplainer` exactly:

- `numpy.random.RandomState(seed)`; row 0 is the unmasked URL;
- for each other row, the number of units removed is `randint(1, n + 1)` (so the fully masked string can occur), the removed units are `choice(n, size, replace=False)`;
- distance = cosine distance of the binary row to the all-ones row × 100;
- kernel = sqrt(exp(−d² / 25²)); regressor `Ridge(alpha=1)`.
- Budget: 1,000 samples. Seed: 42 + row_id. The stability seed (pilot only) is 10,042 + row_id.

SHAP and LIME make separate model calls (no shared cache), so timings are honest.

## 4. Measures

- **Ranking:** by |value|; exact ties broken by unit position (earlier first). k = 3.
- **Primary:** top-3 Jaccard between SHAP and LIME.
- **Secondary:** Spearman over all n units (of |value|); sign agreement on the units in both top-3 sets.
- **Per-URL chance (exact):** E[J] for two independent uniformly random 3-subsets of n units, Σ_h P(h) · h/(6 − h), with P(h) hypergeometric. Values: n = 6: 0.3650; 7: 0.3029; 8: 0.2589; 9: 0.2262; 10: 0.2008. Reported per URL as observed minus chance. This is the only null for V3 (explanations cannot be shuffled between URLs, because units differ).
- **Threshold (H1):** mean top-3 Jaccard < 0.50 counts as considerable disagreement. Chance is always reported next to it.
- **RQ1 statistics:** bootstrap 95% CI of the mean (10,000 resamples, seed 42); Wilcoxon signed-rank of J against per-URL chance.
- **RQ2 statistics:** Kruskal-Wallis across predicted classes on **J minus chance**. Raw J by class is reported descriptively only, because chance depends on n and n differs by class.
- **RQ3:** model calls per explanation is primary; wall time is secondary (paired Wilcoxon). The paper states that call counts are set by design: SHAP needs 2^n, LIME always uses 1,000, so SHAP is cheaper on short URLs by construction.
- **LIME fit (Q2):** weighted R² (`score` returned by LimeBase), reported per URL.

## 5. Sample

- **Pilot (smoke test):** 20 test URLs, 5 per V3 predicted class, all eligible. Within each class the eligible pool is split into tertiles of raw segment count and 2, 2, 1 URLs are drawn from the low, middle and high tertiles with `random_state=7`. At least 2 of the 20 must have more than 10 segments; this is asserted. Saved to `results/v3/xai/pilot_sample.csv` before any model call.
- **Main sample:** per predicted class, `n_class` eligible test URLs drawn with `random_state=42` from the eligible pool minus the pilot URLs.
- **Size rule:** n_class = min(50, floor(7200 s / (4 × t90))), where t90 is the pilot's 90th-percentile per-URL total time (SHAP + LIME at the primary seed, including featurization; excluding the stability seed and the placeholder diagnostic).
- **Timing conditions:** on charger, Windows "Best performance"; one warm-up URL (the first eligible test row by row_id that is not in the pilot) before timing.

## 6. Pilot gates (applied in this order)

The pilot is a smoke test. It tells us about runtime, crashes and gross quality problems, not about the reliability of LIME fit. **The pilot never computes or prints SHAP-vs-LIME agreement.**

- **G0 — hard checks; any failure is a bug, fixed and rerun:**
  - recomputed features of each unmasked pilot URL match its `features_v3_full.parquet` row within 1e-6 absolute;
  - the unmasked stack output matches `test_predictions.csv` within 1e-5 (binding check);
  - Σφ = v(N) − v(∅) within 1e-6;
  - no masked variant crashes or gives a non-finite value.
- **Q1 — signal:** for each URL, the range of v(S) over all coalitions (max − min). The range is ≥ 0.10 in at least 14 of 20 URLs, **and** the median over URLs of the largest single-unit deletion effect max_i |v(N) − v(N \ {i})| is ≥ 0.05.
- **Q3 — LIME stability:** mean top-3 self-Jaccard between the two LIME seeds is ≥ 0.50.
- **R — runtime:** n_class ≥ 25.

**Reported, not gated — Q2 (LIME fit):** median weighted R² for the pilot and later the full run. Interpretation fixed now: if the median is below 0.30, the paper states that LIME's linear surrogate fits the stack poorly on segment masks and treats disagreement as partly a LIME-fit effect, as for the V2 study (mean R² 0.156). Raising the LIME budget is not a remedy for fit: with 6 to 10 units there are at most 1,023 distinct masks.

**Step-down ladder before any fallback:**

1. If Q3 fails: raise the LIME budget to 4,000 and rerun the pilot's LIME only.
2. If R fails: cut LIME to 500 samples (only if LIME dominates the time), then accept n_class down to 25 (100 URLs).
3. If Q1 fails, or the ladder is exhausted: **Draft 4 fallback** — V3 is the classifier, the V2 study is the explanation experiment, kept explicitly separate.

## 7. Pilot diagnostics (no agreement numbers)

- delete vs placeholder: Spearman between SHAP |φ| under the two masking rules (same explainer, so this is about masking robustness, not SHAP-vs-LIME);
- share of masked strings (all coalitions, delete rule) whose hostname parses empty;
- a few example masked strings per URL;
- |v(N) − v(∅)| for information.

## 8. Reporting rules

- No SHAP-vs-LIME agreement on V3 is computed before the main run.
- V3 agreement is not compared with V2's 0.173 as better or worse.
- Agreement is consistency, not correctness.
- Masked URLs (especially deleted hosts such as `.com`) are strings the model never saw; this is stated as a validity limitation, with the placeholder diagnostic as evidence.
- Merging reduces resolution for long URLs (mostly defacement); stated.

## Amendments

None.
