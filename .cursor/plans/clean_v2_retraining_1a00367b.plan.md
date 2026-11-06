---
name: Clean V2 Retraining
overview: Build and evaluate a versioned V2 lexical-feature pipeline on the same cleaned four-class dataset and fixed split, preserving all V1 code/results. Add defensible normalized-URL features, perform bounded validation-only tuning for Logistic Regression, Random Forest, and XGBoost, then evaluate the locked winner on the test set exactly once.
todos:
  - id: version-v2
    content: Create isolated V2 feature, preparation, training, test, artifact, and result paths while preserving the V1 pipeline and outputs.
    status: completed
  - id: implement-features
    content: Implement and unit-test the fixed normalized V2 lexical feature schema and machine-readable feature manifest.
    status: completed
  - id: prepare-verify
    content: Rebuild cleaned data/splits, cache aligned V1/V2 feature matrices, and verify baseline reproducibility and feature ablations.
    status: completed
  - id: tune-models
    content: Run the bounded validation-only LR, RF, and XGBoost searches with fixed weighting strategies and resumable trial logging.
    status: completed
  - id: select-test
    content: Lock the winner by the pre-fixed metric rule, refit on train+validation, and evaluate the untouched test set once.
    status: completed
  - id: verify-report
    content: Validate saved artifacts, tests, lints, metadata, hostname subgroups, and the V1-versus-V2 result comparison.
    status: completed
isProject: false
---

# Clean V2 Model Retraining Plan

## 0. Revisions fixed before execution (override conflicting text below)

- **Eligibility, then selection.** A configuration is eligible only if validation accuracy `> 0.8463`, validation macro-F1 `>= 0.8254`, every malicious-class recall `>= 0.70`, and no malicious-class recall drops more than `0.05` below V1 validation (defacement `0.8859`, malware `0.8808`, phishing `0.7933`) unless macro-F1 `>= 0.8354` (V1 + 0.01). The Section 1 selection rule is applied to eligible configurations only. Tie-breakers after accuracy: higher minimum malicious-class recall, then lower fit time.
- **RF memory budget.** 5.3 GB RAM was free at the start. RF forests are grown in warm-start chunks of 50 trees (identical to a single fit for a fixed seed); a trial stops and is recorded as `skipped_memory_budget` if the projected in-memory tree size exceeds 3 GB. Refinement uses 500 trees or the largest multiple of 50 that fits the budget. The V1-style control is the exact V1 configuration (`200` trees, depth `25`, leaf `5`, `balanced_subsample`) on the locked V2 features.
- **Unseen-host diagnostics.** Every trial also records accuracy and macro-F1 on validation rows whose hostname does not appear in train. These are diagnostics only and are never used for selection.
- **Ablation blocks.** `structural` = the 5 new character counts, path-segment, hostname-label, fragment and embedded-`//` features (12). `lexicon` = `suspicious_token_count`, `is_shortener_host`, `has_punycode` (3). The feature set is locked by the same selection rule (without the eligibility filter).
- **Prefix check.** The first 24 V2 columns must exactly equal the untouched V1 extractor output on every row.
- **Token matching.** The lowercased URL is split into `[a-z0-9]+` tokens; a token counts only on exact membership in the frozen list. Token and shortener lists are frozen in `src/features_v2.py` before any metric is seen.
- **XGBoost.** Early stopping monitors unweighted validation log loss; the resulting slight validation optimism is documented. Final refit uses `best_iteration + 1` trees.
- **Final refit weights** are recomputed from train+validation label counts (same proportions due to stratification).
- **Test-once guard.** `train_v2.py final` refuses to run if `results/v2/test_metrics.json` already exists.
- **V1 artifacts** are no longer on disk; the V1 reference is the saved `results/` files plus the baseline reproduction. V1 model size is taken from the documentation (565 MB).

## 1. Goal, constraints, and success criteria

- Scope is limited to:
  1. extracting lexical features and rebuilding the four-class pipeline;
  2. training and comparing Logistic Regression, Random Forest, and XGBoost with accuracy, macro precision, macro recall, macro-F1, per-class metrics, and confusion matrices.
- Do not implement SHAP, LIME, stacking, ALE, a dashboard, paper writing, or deployment in this stage.
- Preserve the academically defensible V1 findings: normalized conflicts and duplicates remain removed, URL formatting leakage stays excluded, the fixed split remains unchanged, and test data is not used for feature/model decisions.
- V1 reference: normalized Random Forest validation accuracy `0.8463`, validation macro-F1 `0.8254`; test accuracy `0.8471`, test macro-F1 `0.8269`.
- Minimum V2 acceptance gate: validation accuracy must exceed `0.8463` without validation macro-F1 falling below `0.8254` or causing a major minority-class recall collapse.
- Preferred target, not a promise: validation/test accuracy around `0.87–0.90` with improved macro-F1. Do not chase the paper’s `97%` by restoring source-format artifacts.
- Selection rule fixed before training: maximize validation macro-F1; if configurations are within `0.005` macro-F1, choose the one with higher validation accuracy; then compare per-class recall and model size/runtime as tie-breakers.

## 2. Evidence guiding the design

- The local IEEE study uses the same 651,191-URL dataset, 21 lexical features, a 70/30 split, and a five-fold two-level stack: LightGBM, Gradient Boosting, XGBoost, and Random Forest feeding a Random Forest meta-estimator. It reports 97% accuracy and macro-F1 0.95.
- Useful paper-inspired features are first-directory length, TLD length, suspicious-word presence, shortener detection, and embedded-link indicators.
- Do not copy `count-http`, `count-https`, or `count-www`: the V1 audit proved these encode collection-source formatting. The paper also does not specify deduplication, canonicalization, class weighting, random seed, hyperparameters, or exact stacking meta-features, so its score is not an apples-to-apples target.
- Stacking is intentionally excluded because it is outside the stated three-model objective, underspecified by the paper, complicates later TreeSHAP use, and is unnecessary for a one-week MCA project.

## 3. Versioning and file layout

- Keep the current V1 implementation untouched:
  - [`C:\Users\aryan\Downloads\Research\malicious_url_xai\src\features.py`](C:\Users\aryan\Downloads\Research\malicious_url_xai\src\features.py)
  - [`C:\Users\aryan\Downloads\Research\malicious_url_xai\prepare.py`](C:\Users\aryan\Downloads\Research\malicious_url_xai\prepare.py)
  - [`C:\Users\aryan\Downloads\Research\malicious_url_xai\train.py`](C:\Users\aryan\Downloads\Research\malicious_url_xai\train.py)
  - existing [`results`](C:\Users\aryan\Downloads\Research\malicious_url_xai\results) files.
- Add a separate V2 path:
  - `src/features_v2.py`: V2 schema and deterministic extraction;
  - `prepare_v2.py`: rerun the existing cleaning/split code and cache V2 features;
  - `train_v2.py`: bounded tuning, winner selection, final refit, and one-time test evaluation;
  - `tests/test_features_v2.py`: feature and schema tests;
  - `artifacts/v2/`: generated Parquets, final model, encoder, feature manifest;
  - `results/v2/`: all V2 metrics and run metadata.
- Reuse [`src/data.py`](C:\Users\aryan\Downloads\Research\malicious_url_xai\src\data.py) without changing its cleaning or split behavior.
- Do not overwrite `artifacts/final_model.joblib` or any existing V1 output.

## 4. V2 feature schema

Start with all 24 V1 normalized lexical features in their existing order, then append a fixed set of approximately 15 features. Definitions are frozen before metrics are inspected.

### Existing V1 features retained

- Lengths: URL, host, path, query.
- Character counts: `.`, `-`, `_`, `/`, `?`, `=`, `@`, `&`, `%`.
- Letter/digit counts and digit/special-character ratios.
- Subdomain count, path depth, query parameter count.
- IP-host, explicit-port, percent-encoding indicators.
- Shannon entropy.

### New V2 features

- `count_colon`, `count_hash`, `count_plus`, `count_tilde`, `count_semicolon`: literal character counts.
- `first_dir_len`: length of the first non-empty path segment; zero when absent.
- `longest_path_segment_len`: maximum non-empty path-segment length; zero when absent.
- `tld_len`: length of the final hostname label; zero for IP/empty hosts.
- `host_label_count`: non-empty hostname-label count; zero for IP/empty hosts.
- `max_host_label_len`: maximum hostname-label length; zero for IP/empty hosts.
- `fragment_len`: URL fragment length.
- `embedded_double_slash_count`: `//` occurrences after the parsed hostname, capturing embedded links without counting a removed scheme.
- `suspicious_token_count`: case-insensitive count of a pre-fixed small token list such as `login`, `signin`, `verify`, `secure`, `account`, `update`, `confirm`, `bank`, `paypal`, `password`, `credential`, `bonus`, `free`, and `service`; delimiters and matching behavior documented in code.
- `is_shortener_host`: exact/case-insensitive hostname membership in a fixed list of common shorteners such as `bit.ly`, `tinyurl.com`, `t.co`, `goo.gl`, `ow.ly`, `is.gd`, `buff.ly`, and `cutt.ly`; no network lookup.
- `has_punycode`: whether any hostname label begins with `xn--`.

### Feature safety requirements

- Features use only the normalized URL string and standard-library parsing; no label, source, WHOIS, DNS, page fetch, or external lookup.
- Do not add scheme, HTTP/HTTPS, or leading-`www` indicators.
- Parsing malformed URLs must return deterministic finite numeric values rather than fail.
- Keep one canonical ordered list `FEATURE_NAMES_V2`; assert extracted vector length and DataFrame column order against it.
- Save a machine-readable manifest with feature names, definitions/version, suspicious-token list, shortener list, normalization version, and extraction timestamp.

## 5. `prepare_v2.py` implementation

- Read the same `malicious_phish.csv` path used by V1.
- Call existing `load_raw`, `clean`, and `assign_splits` so V2 independently rebuilds the pipeline rather than silently trusting old caches.
- Assert the known reproducibility checkpoints unless the source file has intentionally changed:
  - raw rows: 651,191;
  - clean rows: 631,179;
  - split sizes: 441,825 train, 94,677 validation, 94,677 test;
  - no overlap between split indices;
  - class set exactly benign, defacement, malware, phishing.
- Extract both matrices needed for controlled comparison:
  - `features_v1_norm.parquet`: the unchanged 24-feature baseline on the same clean rows;
  - `features_v2_norm.parquet`: the full V2 feature set.
- Use aligned indices and assert row counts, index equality, no NaN/infinity, and deterministic column order.
- Save `artifacts/v2/clean.parquet`, both feature Parquets, and `results/v2/data_audit.json`.
- Save timing and peak-process-memory information when practical; extraction should remain sequential and simple unless profiling proves it is a bottleneck.

## 6. Feature-value verification before tuning

- Run unit tests first.
- Run a baseline reproduction with the original 24 features and original RF configuration; require results to match V1 within normal deterministic tolerance.
- Run a feature-only ablation using the same original RF configuration:
  - V1 24 features;
  - V1 plus structural features;
  - V1 plus token/shortener features;
  - full V2 feature set.
- Evaluate these only on validation. Save accuracy, macro precision/recall/F1, per-class recall, fit time, prediction time, and feature count to `results/v2/feature_ablation_val.csv`.
- If the full feature set is worse, retain only a feature block that improves or preserves macro-F1; do not inspect test results to make this choice.
- Inspect feature distributions for constant or near-constant additions. Remove only demonstrably broken/constant features, recording the reason in the manifest.

## 7. Class-weight strategies

To improve accuracy without abandoning minority classes, compare three pre-fixed strategies using training-label counts only:

- `none`: every row weight 1.
- `sqrt_balanced`: class weight `(N / (K × n_class))^0.5`, providing moderate compensation.
- `balanced`: class weight `N / (K × n_class)`, reproducing full inverse-frequency balancing.

Implementation details:

- Logistic Regression and Random Forest receive a class-weight dictionary.
- XGBoost receives equivalent per-row `sample_weight`.
- Never combine two balancing mechanisms in one trial.
- Save the exact numeric class weights in every trial row and run metadata.

## 8. Bounded validation-only tuning

All trials train on `train` and are scored on `val`. Seeds are fixed at 42, models run sequentially, and discarded models are released before the next trial to protect 16 GB RAM.

### Logistic Regression

- Pipeline: `StandardScaler` followed by multinomial Logistic Regression as supported by scikit-learn 1.7.2.
- Search:
  - `C`: 0.1, 1.0, 10.0;
  - class weights: none, square-root balanced, balanced;
  - `max_iter=2000` initially, increasing only if convergence warnings occur.
- Total: 9 planned trials.
- Record convergence warnings and iteration counts. Logistic Regression remains a required baseline even if it is not competitive.

### Random Forest

Coarse stage:

- `n_estimators=300`;
- `max_depth`: 25 and unlimited;
- `min_samples_leaf`: 1, 3, 5;
- `max_features='sqrt'`;
- class weights: none and square-root balanced;
- `bootstrap=True`, `n_jobs=-1`, seed 42.
- Total: 12 coarse trials.

Refinement stage:

- Take the two best coarse RF configurations by the fixed selection rule.
- Refit each with `n_estimators=500` and compare `max_features='sqrt'` versus `0.5`.
- Include one fully balanced V1-style control if it is not already represented.
- Do not expand the grid after seeing results unless there is a concrete failure such as every tree being severely over/underfit.

### XGBoost

- Objective: `multi:softprob`; evaluation metric: multiclass log loss; `tree_method='hist'`; seed 42; `n_jobs=-1`.
- Search:
  - `max_depth`: 6, 8, 10;
  - `learning_rate`: 0.05, 0.10;
  - `subsample=0.8`;
  - `colsample_bytree=0.8`;
  - up to 1000 estimators;
  - class weights: none and square-root balanced.
- Use validation early stopping (approximately 50 rounds) to identify the effective tree count and prevent unnecessary training.
- Total: 12 planned trials.
- Save best iteration and validation log loss. When final-refitting XGBoost on train+validation, use the selected effective estimator count without test-based early stopping.

### Trial failure handling

- Wrap each trial so one failure records model, parameters, exception, and elapsed time, then continues.
- Save/append `results/v2/model_trials_val.csv` after every trial so an interruption does not lose completed work.
- Do not retain every fitted model; retain trial metrics and only serialize the selected final estimator.

## 9. Metrics and winner selection

For every trial, calculate and save:

- accuracy;
- macro precision, macro recall, macro-F1;
- weighted precision, recall, F1;
- per-class precision, recall, F1, and support;
- confusion matrix or enough predictions to reconstruct it;
- training and validation-prediction time;
- model parameters, class-weight mode, feature-set version, seed, and status.

Create `results/v2/model_comparison_val.csv` containing the best configuration from each required family. Select the overall winner with the pre-fixed rule from Section 1. Save the complete selection rationale, including ties and per-class checks, to `results/v2/selection.json`.

A configuration is rejected despite a small accuracy increase if it produces a clearly unacceptable minority-class collapse, operationalized before execution as either:

- any malicious-class recall below `0.70`; or
- a drop greater than `0.05` in any malicious-class recall relative to the V1 validation baseline without a compensating macro-F1 improvement.

## 10. Final refit and one-time test evaluation

- After feature set, class weighting, model family, and hyperparameters are locked from validation results, refit exactly once on train+validation.
- Evaluate the untouched test set exactly once.
- Save under `artifacts/v2/`:
  - `final_model.joblib`;
  - `label_encoder.joblib`;
  - `feature_names.json`;
  - `feature_manifest.json`;
  - `selected_config.json`.
- Save under `results/v2/`:
  - `test_metrics.json`;
  - `classification_report.txt` and structured CSV;
  - raw and row-normalized confusion matrices;
  - `test_predictions.csv` with row ID, true class, predicted class, and four probabilities;
  - `hostname_subgroup_test.csv` using the existing seen/unseen-host analysis;
  - `run_metadata.json` with Python/package versions, hardware summary, timestamps, seeds, dataset identity, row counts, feature hash/list, selected parameters, and timings.
- Compare V2 against V1 in `results/v2/v1_vs_v2.csv`, covering accuracy, macro metrics, per-class recall, fit time, model size, and seen/unseen-host performance.
- Report the result honestly even if V2 fails to beat V1; do not alter normalization, remove difficult rows, or retune using test results.

## 11. Tests and quality gates

Add focused tests in [`tests/test_features_v2.py`](C:\Users\aryan\Downloads\Research\malicious_url_xai\tests\test_features_v2.py):

- exact feature-name order and vector length;
- deterministic finite output for normal, empty, malformed, IPv4, IPv6, port-bearing, percent-encoded, and Unicode/punycode URLs;
- first-directory and longest-segment lengths;
- TLD/hostname-label behavior and zero values for IP hosts;
- fragments and embedded `//` counting;
- suspicious-token matching, case handling, and no accidental substring inflation where avoidable;
- exact-host shortener matching so `notbit.ly.example.com` is not marked as a shortener;
- scheme/leading-`www` invariance after normalization;
- no HTTP/HTTPS/scheme/`www` feature in the primary V2 schema;
- feature DataFrame index/column stability.

Add a lightweight pipeline smoke test using synthetic rows or a tiny fixture to verify:

- prepare output schemas align;
- model/encoder/feature names serialize and reload;
- `predict_proba` returns finite rows summing approximately to one;
- class-probability column order matches the encoder.

Before a full run: all existing 12 V1 tests plus all V2 tests must pass. After edits, run lint diagnostics on changed files and resolve introduced errors.

## 12. Execution sequence and checkpoints

1. Confirm dataset and environment; record dependency versions and free disk space.
2. Add V2 feature extractor and tests; run the complete test suite.
3. Implement `prepare_v2.py`; run it and validate audit/split/index assertions.
4. Reproduce the V1 baseline from V2 caches.
5. Run validation-only feature-block ablation and lock the V2 feature set.
6. Run Logistic Regression trials.
7. Run Random Forest coarse trials, then bounded refinement.
8. Run XGBoost trials with early stopping.
9. Build best-per-family comparison and lock the winner using the fixed rule.
10. Refit the winner on train+validation and evaluate test once.
11. Generate test outputs, hostname subgroup comparison, V1-vs-V2 comparison, and metadata.
12. Verify artifacts reload and predictions/probabilities are valid; rerun tests and lint checks.

Expected rough laptop runtime: feature preparation a few minutes; LR trials several minutes; RF trials approximately 15–30 minutes; XGBoost trials approximately 15–40 minutes; final refit/output generation several minutes. Actual timing is recorded rather than assumed. Ensure several GB of free disk because V1 RF was approximately 565 MB and multiple Parquets/models are generated.

## 13. Stop conditions and risk controls

- Stop expanding tuning after the fixed grids/refinement; this avoids endless accuracy chasing and validation overfitting.
- Stop and diagnose if the baseline reproduction materially differs from V1 before trusting V2 comparisons.
- If memory pressure occurs, lower concurrent memory use and process models sequentially; do not silently sample the dataset.
- If XGBoost API behavior differs under version 3.2.0, adapt early-stopping placement while preserving the planned search and recorded best iteration.
- If no V2 configuration passes the acceptance gate, retain V1 as the selected model and document V2 as a negative result; optionally choose the strongest V2 only as an experimental candidate, not as the final model.
- Do not change the fixed test set, inspect test performance during tuning, add source-format leakage features, or claim the paper’s 97% is reproducible under the cleaned protocol.