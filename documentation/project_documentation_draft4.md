# Project Documentation Draft 4 — Direction Document

> **Project:** Detection of Malicious URLs Using Machine Learning and Explainable AI
> **Written:** 14 Nov 2026. **Updated:** 16 Nov 2026 with the result of the V3 main experiment (section 3.6). Stages 1–5 are done; the web app is next.
> **What this draft is:** the single place that states the idea, the proposal, where the project stands, what happens next, and a plain-English guide to every technical term.
> **What this draft is not:** a results log. Drafts 1–3 and the day logs remain the detailed record of V1, V2 and V3. Nothing in them is withdrawn.
> **What this draft changes:** it replaces the "next work" lists in the earlier drafts, and it changes the reporting decision in Draft 3 §12.3. The plan is now to explain the V3 model itself. "V3 as classifier, V2 as explained model" becomes the fallback only.

Contents:

- Part 1 — The idea
- Part 2 — Proposal draft
- Part 3 — Where we stand
- Part 4 — What happens next
- Part 5 — Plain-English guide for a beginner in AI/ML

---

# Part 1 — The idea

## 1.1 In one paragraph

We build a program that reads a web address (URL) and decides whether it is benign, phishing, malware or defacement, using only the text of the URL. We then ask two popular "explanation" tools, SHAP and LIME, why the program made each decision, and we measure whether the two tools give the same reasons and how long each takes. Other studies show SHAP or LIME output for URL classifiers; we measure whether the two can be trusted to agree.

## 1.2 Two deliverables from one codebase

| | Sem 3 — MCARP31 Research Project | Sem 4 — MCARP42 Research Paper |
|---|---|---|
| What is judged | A proposal and a working solution, with report and presentation | One externally validated paper |
| What we hand in | The V3 classifier, a small web app that classifies a URL and shows which parts of it drove the result, the test suite, the report | A short conference paper on SHAP vs LIME agreement for malicious-URL classification |
| What it reuses | The explanation function built for the paper's experiment | The classifier, data cleaning and findings from the project |

The explanation function is written once. The paper's experiment runs it on a sample of URLs and measures agreement. The web app runs it on one URL and displays the result.

## 1.3 Why this research gap

"ML + SHAP for malicious URL detection" already has indexed papers from 2022 onward with reported accuracy of 97% and above. Repeating that is a re-implementation. Three possible gaps were considered:

| Gap | Decision | Reason |
|---|---|---|
| Measure SHAP vs LIME agreement, with timing as a side result | **Chosen** | No new data collection; sits on top of a standard pipeline; the surveyed papers show one explainer, or both side by side, without measuring agreement |
| Add network/behavioural features (WHOIS, page content) | Rejected | Needs live lookups; the dataset's URLs are old and mostly dead; highest time risk |
| Low-latency XAI for real-time or browser use | Not a contribution on its own | Kept only as the timing measurement inside the chosen gap |

The novelty claim is modest and depends on Paper 5 (Nair & Di Troia, 2025), which compares SHAP and LIME for malicious URLs. Its full text has not been read. Aryan owns that check. If it already measures agreement, this work is framed as an extension (cleaned data, final stacked model, aligned segment-level comparison, timing).

---

# Part 2 — Proposal draft

## 2.1 Title

Detection of Malicious URLs Using Machine Learning and Explainable AI: A Comparative Study of SHAP and LIME Explanation Agreement and Efficiency

## 2.2 Background

Malicious URLs are used for phishing, malware delivery and website defacement. Machine-learning classifiers can flag them from the URL text alone, without visiting the site. Because such classifiers are hard to inspect, recent studies attach explanation methods, most often SHAP or LIME, to show which properties of a URL led to a prediction.

An explanation is only useful to an analyst if it is dependable. If two accepted methods give different reasons for the same prediction of the same model, the analyst has no basis for choosing between them. Producing an explanation also costs time on top of the prediction, and that cost is rarely reported.

## 2.3 Problem statement

Studies that explain malicious-URL classifiers usually apply one explanation method, or show two side by side, without measuring whether the methods agree. This project builds a four-class URL classifier on cleaned data and measures, for the same model and the same predictions, how consistently SHAP and LIME identify the influential parts of a URL and how their computational costs compare.

## 2.4 Research questions

- **RQ1.** When SHAP and LIME explain the same prediction of the final classifier, using the same way of hiding parts of the URL, how well do they agree on the most influential parts?
- **RQ2.** Does that agreement differ across the predicted classes (benign, defacement, malware, phishing)?
- **RQ3.** How do SHAP and LIME differ in the time and number of model calls needed per explanation?

A supporting question has already been answered on the way (Part 3, Finding 2): how well do the standard off-the-shelf tabular versions of SHAP and LIME agree on an intermediate single-model classifier?

## 2.5 Hypotheses for the final-model experiment

These are written before the experiment is run.

| | Null hypothesis | Alternative |
|---|---|---|
| H1 | Mean top-k agreement between SHAP and LIME is at or above the fixed threshold | Mean top-k agreement is below the threshold (considerable disagreement) |
| H2 | Agreement does not differ across predicted classes | Agreement differs across predicted classes |
| H3 | Per-explanation time is the same for both methods | Per-explanation time differs |

The value of k, the threshold and the minimum URL length are fixed in the protocol (Part 4, Stage 3) before any agreement number is produced. They must not be changed afterward.

**Outcome (added 16 Nov 2026; the table above is unchanged).** H1 was not supported: mean top-3 agreement is 0.797, above the 0.50 threshold. H2 was supported. H3 was supported, largely by design. Details are in section 3.6.

## 2.6 Objectives

1. Review the literature on ML-based malicious-URL detection and XAI.
2. Clean a public four-class URL dataset and remove formatting that reveals the label.
3. Build and compare classifiers on URL-text features and select a final model using validation data only.
4. Explain the final model's predictions with SHAP and LIME through the same URL-segment masking.
5. Quantify agreement (top-k Jaccard, rank correlation) overall and per class, against a chance level.
6. Measure explanation time and model calls for both methods.
7. Examine individual cases, including cases where the classifier is wrong.
8. Package the classifier and explanation as a small web application.

## 2.7 Scope

**In scope:** URL-text features only; one public dataset; classical ML (tree ensembles); explanation experiment on a sample of test URLs; a local web app for demonstration.

**Out of scope:** page content, WHOIS, DNS or network features; deep learning; a browser extension; real-time deployment; a second dataset.

## 2.8 Method

**Data.** The public Kaggle malicious-URL dataset (`malicious_phish.csv`, 651,191 URLs, four classes).

**Cleaning.** Remove the leading scheme (`http://`, `https://`) and one leading `www.`; delete every URL that then carries two different labels; keep one copy of each remaining URL. This leaves 631,179 URLs.

**Split.** Fixed stratified 70/15/15 train/validation/test split, seed 42, used by every version.

**Features and model.** 48 hand-written measurements of the URL (lengths, character counts, entropy, structure, brand signals) plus 300 character-chunk (3- and 4-character TF-IDF) features, 348 in total. Two boosted-tree models (XGBoost, LightGBM) each output four class probabilities, and a Logistic Regression combines them into the final prediction.

**Explanation experiment.** Each URL is cut into segments. A perturbed URL is made by hiding some segments; all 348 features are recomputed from the perturbed text; the complete stacked model is called. SHAP and LIME both work on this same procedure and both explain the model's own predicted class.

```text
URL  ->  segments  ->  hide some segments  ->  rebuild URL text
     ->  recompute all 348 features  ->  XGBoost + LightGBM  ->  Logistic Regression
     ->  probability of the predicted class
```

**Measures.** Top-k Jaccard and Spearman rank correlation per URL; chance-level agreement for comparison; LIME's local fit (R²); time and model calls per explanation.

**Statistics.** Bootstrap confidence intervals for means; Kruskal-Wallis across classes; Wilcoxon signed-rank for paired timing.

## 2.9 Contributions the paper will claim

The paper explains one model, V3. The other items are findings made on the way to it.

1. **Main result (section 3.6):** on the final stacked classifier, SHAP and LIME largely agree when both use the same URL-segment masking (mean top-3 Jaccard 0.797, chance 0.269). Changing the masking rule changes the explanation more than changing the explainer (0.492 against 0.797). Agreement differs by predicted class.
2. **Finding on the way — dataset leakage:** in this widely used dataset, URL formatting reveals the class. Removing it lowers a baseline's accuracy from 94.02% to 84.71% and exposes 4,047 URLs with contradictory labels.
3. **Finding on the way — default tooling disagrees:** on the intermediate 36-feature XGBoost model, off-the-shelf TreeSHAP and LIME Tabular share few top features (mean top-5 Jaccard 0.173) and LIME fits the model poorly (mean local R² 0.156). This motivated the segment-based design. It is consistent with the main result (how the input is perturbed matters), but it is not a controlled comparison with it.
4. **Classifier:** 94.85% accuracy and 0.9338 macro-F1 on cleaned data, with seen/unseen hostname results reported.

Whether item 2 has been reported elsewhere has not been checked.

## 2.10 Limitations to state openly

- One dataset; no external validation.
- Random URL-level split: 75.3% of test URLs share a hostname with training data. Accuracy is 96.83% on seen hostnames and 88.81% on unseen ones.
- The test partition was reported for V1 and V2 before V3 was designed, so the V3 score is held out but not fully independent.
- Character-chunk features may memorise campaigns or hostnames.
- Agreement between explainers measures consistency, not correctness. Neither is ground truth.
- Hiding segments creates URLs that never existed; they are real strings but may be unusual.
- Short URLs have too few segments for a top-k comparison and are excluded. The 6-segment rule keeps 66.2% of test URLs but only 34.7% of predicted-phishing URLs.
- Only two masking rules were tried, and the explanation depends on which one is used.
- Sharing the same masks makes SHAP and LIME close relatives (KernelSHAP is formally LIME with a particular kernel), so some agreement is expected.

---

# Part 3 — Where we stand

## 3.1 What exists

| Version | Role in the story | Model | Inputs | Test accuracy | Macro-F1 |
|---|---|---|---:|---:|---:|
| V1 | Baseline; proves the leakage | Random Forest | 24 | 0.8471 | 0.8269 |
| V2 | Intermediate; preliminary SHAP/LIME study | XGBoost | 36 | 0.9089 | 0.8863 |
| V3 | **Final model; the one to be explained** | XGBoost + LightGBM + Logistic Regression stack | 348 | **0.9485** | **0.9338** |

V3 per-class F1: benign 0.9648, defacement 0.9807, malware 0.9594, phishing 0.8304. Phishing is the weakest class; 2,436 phishing URLs in the test set are predicted benign.

Checked on 14 Nov 2026: `python train_v3.py verify` reloads the saved V3 model and reproduces its saved test probabilities. Checked on 15 Nov 2026: all 70 tests pass and the V3 checksum freeze is clean.

## 3.2 Finding 1 — the dataset leaks its labels

Share of raw URLs that begin with a scheme:

| Class | Has scheme |
|---|---:|
| Benign | 8.3% |
| Defacement | 100.0% |
| Malware | 96.3% |
| Phishing | 26.4% |

The classes were collected from different sources that wrote URLs differently, so "does it start with http://" predicts the class without saying anything about maliciousness. Evidence, using the same V1 Random Forest on the test set:

| Input | Features | Accuracy |
|---|---:|---:|
| Cleaned URL | 24 | 0.8471 |
| Raw URL, same features | 24 | 0.9402 |
| Raw URL plus explicit scheme flags | 26 | 0.9466 |

Cleaning also exposed 4,047 URLs that appear once as phishing and once as benign, differing only by scheme or `www.`. All 8,230 such rows were removed.

## 3.3 Finding 2 — preliminary SHAP vs LIME study on V2

Setup: frozen V2 XGBoost, 500 test URLs (125 per predicted class), exact TreeSHAP vs LIME Tabular, top-5 of 36 features, threshold 0.50 fixed in advance.

| Result | Value |
|---|---:|
| Mean top-5 Jaccard | 0.1730 (95% CI 0.1571–0.1889) |
| URLs below the 0.50 threshold | 95.6% |
| Mean rank correlation (Spearman) | -0.0101 |
| LIME mean local R² | 0.1560 |
| Median time, TreeSHAP | 224.19 ms |
| Median time, LIME | 60.85 ms |

| Predicted class | Mean Jaccard |
|---|---:|
| Benign | 0.0487 |
| Defacement | 0.2491 |
| Malware | 0.3514 |
| Phishing | 0.0430 |

**Null baselines (post-hoc, added 15 Nov 2026 after the results were seen).** Source: `results/v2/xai/null_baseline.json`, computed from the saved CSVs only. Two baselines are reported:

- **Uniform chance:** two random picks of 5 features out of 36 give a mean Jaccard of 0.0817 (exact).
- **Same-class null:** the SHAP explanation of one URL paired with the LIME explanation of every other URL with the same predicted class (all pairs). A permutation test (10,000 within-class shuffles, seed 42) gives the p-value.

| Predicted class | Observed Jaccard | Same-class null | Observed Spearman | Same-class null Spearman |
|---|---:|---:|---:|---:|
| Benign | 0.0487 | 0.0351 | -0.1598 | -0.1812 |
| Defacement | 0.2491 | 0.2152 | 0.0657 | 0.0446 |
| Malware | 0.3514 | 0.2514 | 0.2230 | 0.1560 |
| Phishing | 0.0430 | 0.0262 | -0.1694 | -0.2070 |
| All (class-balanced) | 0.1730 | 0.1323 | -0.0101 | -0.0466 |

Every observed value is above its same-class null (permutation p = 0.0001, the smallest possible with 10,000 shuffles). Benign and phishing are below uniform chance, but mismatched URLs of the same class agree even less, and their rank correlations are more negative still. So the negative correlations are a class-level habit of the two tools (each favours a different set of features for that class), not the two methods reversing each other on individual URLs. The per-URL signal is real but small: about 0.04 Jaccard above the same-class null overall.

Two weaknesses of this study explain why it is preliminary:

- TreeSHAP values were in the model's raw score (log-odds) space while LIME explained probabilities, so only ranks could be compared.
- LIME's straight-line approximation fitted the model poorly, so part of the disagreement is LIME failing, not two sound methods disagreeing.

## 3.4 Known issues

| Issue | Status |
|---|---|
| V3 is at 94.85%, not 95% | Accepted. Report 94.85%. No further tuning against the test set. |
| The paper's main experiment | Done on 15 Nov 2026 (section 3.6). H1 was not supported, so the paper's headline changes. |
| V3 misjudges some everyday URLs | See below. Handled in the web app and reported as a limitation. |
| Paper 5 full text unread | Aryan's task. The novelty wording waits on it. |
| Dataset citation | Dataset is public and was downloaded from Kaggle. Copy the exact page title, author and licence line into the references. |
| Venue indexing of surveyed papers | Still unverified. |
| V3 has no checksum freeze | Done: `results/v3/freeze.json` (46 files). |

**Everyday URLs.** Eight URLs were tried with `check.py` on 14 Nov. Five were sensible (GitHub login, Wikipedia and YouTube as benign; an Amazon cart URL as benign but only narrowly, 51% against 47% phishing; an IP-and-port URL as malware). Three were not:

| URL | V3 prediction |
|---|---|
| `https://www.google.com` | phishing, 88.0% |
| `https://mail.google.com/mail/u/0/` | phishing, 92.9% |
| `http://paypal.com.secure-login.verify-account.xyz/update` | benign, 91.3% |

Eight URLs is an anecdote, not a measurement. The likely cause is the dataset: its short, bare-domain URLs are mostly phishing, and its benign URLs are mostly long paths.

## 3.5 Decisions taken on 14 Nov

| Decision | Detail |
|---|---|
| Final model | V3 stack, frozen. 94.85% is reported as is. |
| Model explained in the paper | V3 only. V1 and V2 appear as the route to it. |
| V2 SHAP/LIME study | Kept as a preliminary finding, not deleted. |
| How V3 is explained | URL-segment masking with all 348 features recomputed. Never by perturbing the 348 columns independently, and never by explaining one base model in place of the stack. |
| Sem 3 package | A Streamlit web app, not a browser extension. |
| Explanation wording in the app | Based on URL parts the model sees. "No HTTPS" cannot be a reason, because the scheme is removed before the model sees the URL. |
| Well-known sites in the app | A small, disclosed allowlist in the app layer; demo mainly on held-out test URLs. |
| Order of work | Experiment first, app second, report and slides last. |

## 3.6 Finding 3 — the main experiment on V3 (run 15 Nov 2026)

Source: `malicious_url_xai/results/v3/xai/main/xai_summary.json`. Protocol: `documentation/v3_protocol.md` with Amendment 1. Code commit `1a6e490`; the run was on charger with Windows Best performance.

Setup: 200 test URLs, 50 per predicted class, each with at least 6 segments, pilot URLs excluded. Exact Shapley values against LIME with 1,000 samples. Both explain the stack's probability for its predicted class. The primary masking rule deletes a segment; the secondary rule (Amendment 1) replaces it with `x` characters of the same length.

**RQ1 — do they agree? Yes. H1 is not supported.**

| Result (delete rule) | Value |
|---|---:|
| Mean top-3 Jaccard | 0.797 (95% CI 0.760–0.833) |
| Mean chance level | 0.269 |
| Mean Jaccard minus chance | 0.528 (95% CI 0.490–0.566); Wilcoxon p = 1.8e-34 |
| URLs with identical top-3 sets | 123 of 200 |
| URLs sharing two of three | 70 |
| URLs sharing one of three (below the 0.50 threshold) | 7 (3.5%) |
| Mean rank correlation (Spearman) | 0.831 |
| Same sign on shared top-3 segments | 100% |

**RQ2 — does agreement differ by class? Yes. H2 is supported.**

| Predicted class | Mean units | Mean Jaccard | Chance | Minus chance | LIME median R² |
|---|---:|---:|---:|---:|---:|
| Benign | 8.22 | 0.884 | 0.267 | 0.617 | 0.69 |
| Defacement | 9.16 | 0.920 | 0.231 | 0.689 | 0.75 |
| Malware | 7.34 | 0.744 | 0.299 | 0.445 | 0.73 |
| Phishing | 7.92 | 0.640 | 0.278 | 0.362 | 0.46 |

Kruskal-Wallis on Jaccard minus chance: H = 56.95, p = 2.6e-12. This class order belongs to the delete rule. Under placeholder masking the class means are benign 0.75, defacement 0.89, malware 0.79 and phishing 0.77, so "phishing agrees least" must always be stated together with the rule. Only 6 of the 200 predictions are wrong, which is too few to compare right and wrong predictions.

**RQ3 — cost. H3 is supported, largely by design.**

| | Exact SHAP | LIME |
|---|---:|---:|
| Model calls per explanation | 2^n: median 256 (64 to 1,024) | always 1,000 |
| Median wall time | 143.6 ms | 438.8 ms |

SHAP needs fewer calls on 60% of URLs. Paired Wilcoxon on wall time: p = 7.0e-29. At 10 units (80 of the 200 URLs) the two take the same time, about 440 ms. The difference comes from how many times the model is called, not from one method being cleverer.

**The masking rule matters more than the explainer** (comparison declared in Amendment 1, after the pilot and before the main run).

| Comparison | Mean top-3 Jaccard |
|---|---:|
| SHAP vs LIME, both with delete | 0.797 |
| SHAP vs LIME, both with placeholder | 0.800 |
| SHAP with delete vs SHAP with placeholder | 0.492 (95% CI 0.457–0.529) |
| LIME with delete vs LIME with placeholder | 0.510 (95% CI 0.473–0.546) |

Paired test of the first row against the third: the explainer pair agrees more on 125 URLs, less on 15, equally on 60 (Wilcoxon p = 5.2e-18).

**The phishing baseline.** For 34 of 50 phishing URLs the model is more confident of "phishing" when every segment is deleted than for the full URL (mean 0.915 against 0.860). For the other three classes this never happens. A string of bare punctuation looks like phishing to this model, so for phishing the segments mostly pull the score down from a high starting point. This is a likely reason masking matters so much, and it looks like the same dataset habit as the Google case in section 3.4; neither link has been tested.

**How the paper is written from this.**

- H1 is reported as not supported. The hypothesis, k = 3 and the 0.50 threshold are not rewritten.
- The headline is the masking finding, followed by the class differences. The agreement number alone is the weaker claim, because SHAP and LIME on the same masks are close relatives.
- Finding 2 (V2) is used as a contrast that is consistent with this result. The numbers 0.173 and 0.797 are not placed in one table, because the units differ.
- The masking comparison is described as declared before the main run, not as planned from the start.

---

# Part 4 — What happens next

## 4.1 Stages

| # | Stage | Output | Done when |
|---|---|---|---|
| 1 | Null baseline on the V2 results | Observed vs shuffled same-class agreement, written to a separate file `results/v2/xai/null_baseline.json` | Uses saved CSVs only; no explanation is regenerated and no existing result file is touched |
| 2 | Freeze V3 | `results/v3/freeze.json` with checksums of everything in `artifacts/v3/`, the saved V3 results and the feature and training source files | Explanation scripts refuse to run if a frozen file changes |
| 3 | Write the V3 experiment protocol | `documentation/v3_protocol.md`, fixing every choice listed in 4.2 | Aryan approves it before any explainer code runs |
| 4 | Build the segment explainer and run a 20-URL pilot (5 per predicted class) | One explanation function; pilot runtime, segment counts, LIME fit, sample perturbed URLs | The protocol's gates are applied and the full-run sample size is set |
| 5 | Full experiment and analysis | Per-URL agreement, per-class results, chance level, timing, figures | Results saved to `results/v3/xai/` |
| 6 | Web app | Streamlit page: URL in; class, probabilities and highlighted segments out | Runs locally on demo URLs |
| 7 | Report and slides | LaTeX report, presentation | Submitted |

**Status on 16 Nov 2026: stages 1–5 are done.** The null baseline is in section 3.3, the freeze is `results/v3/freeze.json`, the protocol is `documentation/v3_protocol.md`, the pilot passed every gate (`results/v3/xai/pilot/`), and the main result is in section 3.6. No fallback was needed. Stage 6, the web app, is next.

The working plan for stages 1–4 was `.cursor/plans/v3_freeze,_null,_protocol,_pilot_4a645f5a.plan.md` (completed).

## 4.2 Protocol choices (now fixed)

These were proposals when this section was written. They are now fixed in `documentation/v3_protocol.md`, which is the reference; Amendment 1 there adds placeholder masking as a secondary analysis. The table is kept as the plain-language summary.

| Choice | Proposed default | Why |
|---|---|---|
| Segment | Each unbroken run of letters and digits in the cleaned URL (`paypal.com/account/verify?id=123` gives `paypal`, `com`, `account`, `verify`, `id`, `123`) | Simple, deterministic; segment-count statistics are already known for this rule |
| Masking | Remove the segment's characters and leave the punctuation in place; one shared function used by both explainers | Identical perturbations for both methods |
| Output explained | The stack's probability for its own predicted class | Both methods in probability space, which removes the log-odds vs probability mismatch of the V2 study |
| Unit cap | At most 10 units per URL; a URL with more than 10 segments has neighbouring segments merged into 10 groups | Keeps the number of possible masks at 1,024 or fewer, so SHAP can be exact |
| SHAP | Exact Shapley values over the units, computed from every possible mask (at most 1,024 model calls per URL); never sampled | No dependence on tree internals, so the whole stack is explained; no sampling noise on the SHAP side |
| LIME | Linear surrogate fitted on the same kind of masks with LIME's usual sampling and distance weighting, fixed seed, 1,000 samples, a weight for every unit | Same inputs as SHAP; only the method differs |
| k | 3 | Median URL has 7 segments; top-5 is meaningless for short URLs |
| Minimum segments | 6 | Keeps top-3 away from "all segments" |
| Threshold | Mean top-3 Jaccard below 0.50 counts as considerable disagreement | Top-3 Jaccard can only be 0, 0.2, 0.5 or 1.0; below 0.50 means at most one shared segment |
| Sample | Up to 200 test URLs, up to 50 per V3 predicted class, seed 42; the per-class number is set from the pilot's timing so the full run fits in about two hours, and must be at least 25 | Class-balanced like the V2 study; protects the deadline |
| Chance level | Random-ranking agreement computed for each URL's own unit count (0.37 at 6 units, 0.20 at 10) | Segments differ per URL, so explanations cannot be shuffled between URLs |
| Class comparison | Tested on agreement minus chance, not on raw agreement | Classes differ in URL length, and chance depends on length |
| Cost comparison | Model calls per explanation first, wall time second | Exact SHAP needs between 64 and 1,024 calls and LIME always 1,000, so time is largely set by design |
| Pilot gates | Hard checks (recomputed features and predictions match the saved ones; Shapley values add up); signal (hiding segments must move the model's output); LIME stability across two seeds; runtime | Stops a broken or uninformative experiment before the full run |
| LIME fit | Reported, with its interpretation written in advance; it does not stop the experiment | The V2 study was reported with a poor fit; a low value is a finding, not a failure |

Segment counts measured on 50,000 random cleaned URLs with the proposed rule: median 7; 33.8% have 5 or fewer; 9.8% have more than 16. Class medians: benign 7, defacement 12, malware 7, phishing 5. A six-segment minimum therefore excludes roughly a third of URLs and at least half of phishing URLs. The excluded share must be reported and the bias toward longer URLs stated as a limitation.

## 4.3 What to expect, and what not to assume

When SHAP and LIME use the same masks and the same model calls, they are close relatives: both fit a weighted linear summary of how the output changes as segments are hidden, and they differ mainly in the weighting and in sampling noise. Agreement may therefore be much higher than the 0.17 seen in the V2 study. That would not be a failure. Set beside Finding 2, it would say that most SHAP/LIME disagreement in practice comes from how each tool represents the input, not from the methods' mathematics. Low agreement would also be reportable. The abstract must not be written around "they disagree" until the numbers exist.

The V2 and V3 numbers must not be described as an improvement or a decline. One compares 36 engineered features; the other compares URL segments.

**What happened (16 Nov 2026).** Agreement was high, 0.797, as this section warned it might be. See section 3.6.

## 4.4 Fallback (not needed)

Before any fallback, the experiment is scaled down: if LIME is unstable its sample budget is raised, and if runtime is too long the LIME budget and then the sample size are reduced, down to 100 URLs (25 per class).

If the signal gate fails, or scaling down is not enough, the paper reverts to the position already documented in Draft 3: V3 is the classifier, the V2 study is the explanation experiment, and the two are kept explicitly separate. Stages 1 and 2 are useful under either outcome.

## 4.5 Web app outline (Stage 6)

- One Streamlit page; the model is loaded once at start. A web app and not a browser extension: the model is a 111 MB Python stack, so an extension would need this backend anyway.
- Input: a URL. It is cleaned the same way as the training data and is never opened or fetched.
- Output: cleaned URL, predicted class, four probabilities, and the URL with its segments coloured.
- One explainer: exact SHAP with the delete rule, the protocol's primary setting. The two explainers agree closely (section 3.6), so showing both adds nothing for a user.
- Two colours: segments that push towards the predicted class and segments that push away from it. No one-directional "flagged because" list, because for most phishing results the segments lower the score (section 3.6).
- "No HTTPS" is never shown as a reason; the scheme is removed before the model sees the URL.
- A line saying how the reasons are computed (parts of the URL are deleted and the URL is re-scored), and a note when the URL has fewer than 6 segments that such URLs were outside the study.
- Allowlist check for a small set of well-known domains, shown on screen as an app-level rule, with the model's own answer still visible. It never enters any reported accuracy figure.
- Example buttons that load held-out test URLs.
- A visible note that this is a research demonstration trained on an old dataset.

## 4.6 Rules that stay in force

- No more model training or tuning. The test set is not used for any further decision.
- Existing result files under `results/` are not regenerated or overwritten.
- Every protocol choice is fixed before the corresponding numbers are seen.
- V2 explanation values are never presented as explanations of V3.

---

# Part 5 — Plain-English guide

This part assumes no background in AI or ML.

## 5.1 The task

A **URL** is a web address such as `paypal.com/account/verify?id=123`. It has parts:

| Part | In the example |
|---|---|
| Scheme | `https://` (removed in this project) |
| Hostname | `paypal.com` |
| Path | `/account/verify` |
| Query | `id=123` |

**Classification** means sorting things into named groups. Our four groups are:

- **Benign** — an ordinary safe page.
- **Phishing** — a fake page that tries to steal passwords or card details.
- **Malware** — a link that delivers harmful software.
- **Defacement** — a page on a hacked website that the attacker has altered.

The program looks only at the text of the address. It never opens the website.

## 5.2 How a computer learns this

**Machine learning** means showing a program many examples with the right answers and letting it find the patterns itself. Our examples are about 631,000 URLs, each with its correct group.

A program cannot read text the way people do, so each URL is first turned into numbers. Each number is called a **feature**. Examples from this project:

- how long the URL is;
- how many dots, slashes or digits it has;
- whether the hostname is a raw IP address like `192.168.1.10`;
- how random the characters look (**entropy**: `xk2q9z` is more random than `login`);
- how closely the hostname resembles a famous brand (`paypa1` is one character away from `paypal`).

V3 also uses **character chunks** (3 or 4 characters long, such as `.com`, `php?` or `logi`). It keeps the 300 most common chunks and records how strongly each appears in a URL. The scoring scheme is called **TF-IDF**; it gives more weight to chunks that are frequent in this URL but not in every URL.

## 5.3 Training, validation and test

The data is split into three piles:

- **Training (70%)** — the program learns from these.
- **Validation (15%)** — used to choose between different programs and settings.
- **Test (15%)** — used at the end to report how good the chosen program is.

The reason is the same as in an exam. If students see the exam paper while studying, their marks say nothing about what they learned. The test pile must not influence any decision. This is why we stopped tuning at 94.85% instead of pushing to 95%: every extra adjustment made after looking at test results makes the test score less honest.

## 5.4 The leakage problem

**Leakage** means the program gets a hint about the answer that it would not have in real use.

In this dataset the benign URLs came from one source and were mostly written without `http://`, while the defacement URLs came from another source and all had it. A program can then score highly just by checking how the address was typed. That is like a teacher who writes all the correct answers in blue ink: students score well by looking at the colour, and learn nothing.

We removed the hint by deleting the scheme and `www.` from every URL. Accuracy of the first model fell from about 94% to 84.7%. The lower number is the honest one. This also explains why our 94.85% should not be compared directly with the 97% in earlier papers that kept those hints.

## 5.5 Measuring how good the model is

- **Accuracy** — out of all URLs, the share labelled correctly. V3: 94.85%.
- **Precision** (for one class) — when the model says "phishing", how often it is right.
- **Recall** (for one class) — of all real phishing URLs, how many the model caught.
- **F1** — one number that balances precision and recall.
- **Macro-F1** — the average F1 over the four classes, each class counting equally.

Accuracy alone can mislead because two-thirds of the data is benign. A program that calls everything benign would be about 67% accurate and useless. Macro-F1 exposes that.

A **confusion matrix** is a table showing, for each true class, what the model called it. It shows which mistakes are common. Ours shows the biggest mistake is real phishing called benign.

**Class weights** tell the model that mistakes on rare classes (malware is under 4% of the data) matter more, so it does not ignore them.

## 5.6 The models

- **Logistic Regression** — draws straight-line boundaries between classes. Simple and fast; it did poorly here because the patterns are not straight lines.
- **Decision tree** — a chain of yes/no questions ("Is the URL longer than 60 characters?", "Does the host contain digits?") ending in an answer.
- **Random Forest** — hundreds of decision trees, each trained on a slightly different view of the data, that vote. This was V1.
- **Boosting (XGBoost, LightGBM)** — trees built one after another, each one concentrating on the mistakes of the trees before it. XGBoost alone was V2.
- **Stacking** — several models give their opinions and another small model learns how to combine them. V3 is a stack: XGBoost and LightGBM are two experts, and a Logistic Regression is the judge that weighs their opinions.

## 5.7 Seen and unseen hostnames

Many URLs in the test pile come from websites that also appear in the training pile. The model may partly recognise the website instead of judging the URL. To check, we report results separately: 96.83% accuracy on hostnames it has seen and 88.81% on hostnames it has not. The second number is closer to what to expect on new websites.

This is also why the model can call `google.com` phishing. In the training data, very short addresses with nothing after the hostname were mostly phishing, so the model learned "short and bare means phishing". It learned the dataset's habits, not the real web.

## 5.8 Why explanations are needed

A model that only says "phishing, 93%" gives an analyst nothing to check. **Explainable AI (XAI)** methods try to say which inputs pushed the model toward its answer. We use two.

**SHAP.** Imagine a team wins a prize and you want to pay each member fairly. You consider every possible sub-team, see how much the result changes when a member joins, and average that. SHAP does this with features: each feature gets a share of the credit for the prediction. **TreeSHAP** is a fast, exact version that works only for tree models.

**LIME.** LIME takes one URL, makes many slightly altered copies, asks the model about each, and then fits a simple straight-line formula that imitates the model near that one URL. The weights in the formula are the explanation.

LIME reports how well its straight line imitates the model, as a number called **R²** between 0 and 1. In our V2 study it averaged 0.156, which means the imitation was poor. An explanation built on a poor imitation should not be trusted much.

## 5.9 Measuring agreement

- **Top-k** — the k most important items in an explanation. We used the top 5 features in the V2 study.
- **Jaccard similarity** — shared items divided by all distinct items. If SHAP's top 5 are A, B, C, D, E and LIME's are A, B, F, G, H, they share 2 out of 8 distinct items, so Jaccard is 2/8 = 0.25. Identical lists give 1; no overlap gives 0.
- **Spearman rank correlation** — compares two full rankings. +1 means the same order, 0 means unrelated, -1 means reversed.
- **Chance level** — what agreement would look like if both methods picked at random. For 5 out of 36 features it is about 0.08. A result near that means the two explanations are effectively unrelated.
- **Null baseline** — a fairer version of chance. We pair each SHAP explanation with a LIME explanation of a different URL from the same class. If real pairs agree no better than these mismatched pairs, the explainers are only reflecting class habits, not the individual URL.

Agreement is not correctness. If both methods agree, both could still be wrong. If they disagree, at least one is unreliable for that prediction.

## 5.10 Why V3 needs a different way of explaining

V3 uses 348 numbers per URL, and 300 of them are character chunks that all come from the same piece of text. LIME's usual approach changes each number independently. That produces combinations no real URL could have, such as "contains `.com`" switched off while "contains `com/`" stays on. The model is then being asked about nonsense.

The fix is to change the URL itself instead of the numbers:

1. Cut the URL into pieces (segments).
2. Hide some pieces.
3. Turn the altered URL back into all 348 numbers.
4. Ask the complete model for its answer.

Both SHAP and LIME then say which pieces of the URL mattered. The result reads naturally: it names pieces such as `verify` and `secure-login`, not "`tld_len` is 3".

There are two ways to hide a piece. **Delete** removes its characters (`paypal.com/verify` becomes `.com/verify`). **Placeholder** replaces them with the letter x (`xxxxxx.com/verify`). The main experiment found that this choice changes which pieces look important more than the choice between SHAP and LIME does.

## 5.11 The statistics, briefly

- **Hypothesis** — a statement to be tested. The **null hypothesis (H0)** says "no difference" or "nothing unusual". We look for evidence against it.
- **p-value** — how likely results at least this extreme would be if the null hypothesis were true. A very small p-value means the null hypothesis is hard to believe.
- **Confidence interval** — a range that likely contains the true average. **Bootstrap** builds it by re-sampling our own results many times.
- **Wilcoxon signed-rank test** — checks whether two paired sets of measurements differ, here SHAP time vs LIME time on the same URLs.
- **Kruskal-Wallis test** — checks whether several groups differ, here agreement across the four classes.
- **Fixing thresholds in advance** — we decide what counts as "disagreement" before looking at results, so the conclusion cannot be bent to fit the data.

## 5.12 Questions an evaluator may ask

**Why is your accuracy lower than the 97% in earlier papers?**
Those results used URLs where the formatting reveals the class. We removed that hint and showed with an ablation that it alone is worth about nine accuracy points. 94.85% is on cleaned data.

**Why not tune further to reach 95%?**
Any further tuning would be guided by the test set, which would make the reported score dishonest.

**Why does it flag Google as phishing?**
The dataset's short bare-domain URLs are mostly phishing, so the model learned that pattern. It is a dataset limitation, stated in the report, and the app handles well-known domains with a disclosed allowlist.

**Why explain URL segments and not the 348 features?**
Changing the 348 numbers independently creates inputs no real URL can produce. Changing the URL text keeps every input consistent and explains the whole stacked model.

**Which explainer is correct?**
Neither is ground truth. The study measures whether they are consistent with each other, which is what an analyst relying on them needs to know.

**Your hypothesis said they would disagree. They agreed. Is the study a failure?**
No. The hypothesis, the threshold and the sample were fixed before the run, and the result is reported as it came out: mean top-3 agreement 0.797 against a threshold of 0.50. A hypothesis that is not supported is still a result.

**If SHAP and LIME agree, can the explanation be trusted?**
Only partly. When the way of hiding a segment was changed from deleting it to replacing it with x's, the top-3 segments of the same explainer overlapped by only about a half (0.492 for SHAP, 0.510 for LIME). The explanation depends on that choice, so the app states which one it uses.

**What did you find that was not planned?**
The label leakage in the dataset and the 4,047 contradictory labels it was hiding.
