---
name: malicious URL XAI
overview: Build a reproducible four-class lexical URL classifier, target roughly 95% accuracy without sacrificing macro-F1, then compare SHAP and LIME agreement and latency on a fixed 500-URL sample. Keep the work isolated from the unrelated existing project and save every intermediate artifact so expensive stages are not rerun.
todos:
  - id: setup-audit
    content: Create the isolated environment/project structure, freeze dependencies, and audit/clean the dataset reproducibly.
    status: pending
  - id: features-splits
    content: Implement and test lexical feature extraction, then cache one fixed stratified train/validation/test split.
    status: pending
  - id: train-evaluate
    content: Train LR, RF, and XGBoost; select by validation macro-F1; evaluate the final model once on test.
    status: pending
  - id: generate-xai
    content: Freeze the 500-URL sample and generate resumable SHAP/LIME explanations with fair per-instance timings.
    status: pending
  - id: analyze-report
    content: Calculate agreement/statistical tests and export report-ready tables, plots, and limitations.
    status: pending
isProject: false
---

# Malicious URL Model and XAI Plan

## Fixed experimental protocol
- Input: [`malicious_phish.csv`](c:/Users/smile/Downloads/0New%20folder/malicious_phish.csv), containing 651,191 rows and four labels.
- Dataset artifact (measured): a scheme prefix appears in 8.3% of benign, 100% of defacement, 96.3% of malware and 26.4% of phishing URLs; `https://` in only 0.5% of benign URLs; leading `www.` in 3.1% of benign vs 69.8% of defacement. These reflect source formatting, not maliciousness.
- Normalize every URL before feature extraction: strip surrounding whitespace, remove the scheme (`scheme://`) and one leading `www.` (case-insensitive). Do not lowercase or otherwise rewrite paths.
- Remove every normalized URL that carries conflicting labels, then keep one row per normalized URL. Report the resulting counts (they will differ from the raw 6 conflicts / 10,072 duplicates).
- Primary model uses normalized-URL features only (no HTTPS flag, no has-scheme flag). Raw-URL ablation: train the selected model type once on features from the raw URL (including HTTPS/has-scheme flags) on the same split rows, and report the score difference as evidence of format leakage.
- Use `random_state=42` everywhere and a stratified 70/15/15 train/validation/test split. Keep the test set untouched until the final model is selected.
- Primary selection metric: macro-F1. Secondary metrics: accuracy, macro precision, macro recall, per-class recall, and confusion matrix. Approximately 95% accuracy is a target, not a result to force.
- Fix XAI choices before running: 500 test URLs (125 per predicted class, sampled from all test predictions with a saved `correct` flag), `k=5`, and “considerable disagreement” when mean top-5 Jaccard is below 0.50. The overall mean is class-balanced by design; state this.

## Project structure
Create a separate [`malicious_url_xai`](c:/Users/smile/Downloads/0New%20folder/malicious_url_xai) folder:
- `src/features.py`: deterministic URL parsing and lexical feature extraction.
- `src/data.py`: cleaning, label encoding, and split creation.
- `train.py`: train and compare models; save metrics and the selected model.
- `explain.py`: generate SHAP/LIME explanations and raw timing records once.
- `analyze.py`: agreement statistics, hypothesis tests, tables, and plots.
- `tests/test_features.py`: small feature-extraction checks.
- `artifacts/`: cleaned split indices, feature matrices, encoders, and models.
- `results/`: CSV/JSON metrics, explanations, statistical results, and figures.

## 1. Environment and reproducibility
- Create and activate `.venv`.
- Install `pandas numpy scikit-learn xgboost shap lime scipy matplotlib seaborn joblib pytest` (XGBoost, SHAP, and LIME are currently unavailable in the active Python environment).
- Freeze the resolved versions to `requirements-lock.txt`; record Python version, CPU, RAM, dataset filename, seed, and run timestamp in `results/run_metadata.json`.
- Add a short `README.md` containing setup and the exact execution order: `pytest`, `train.py`, `explain.py`, `analyze.py`.

## 2. Audit and clean the dataset
- Validate that columns are exactly `url,type`, values are non-null, and labels are only `benign`, `phishing`, `malware`, and `defacement`.
- Save before/after row counts, class counts, duplicate count, conflicting-label count, and URL-length summary to `results/data_audit.json`.
- For conflicting normalized URLs, remove every occurrence rather than arbitrarily choosing a label. Retain one row per normalized URL (keep the raw string of the first occurrence for the ablation).
- Encode labels with `LabelEncoder`, save the class mapping, and save split row IDs so every later script uses the identical split.
- Record hostname overlap across splits as a limitation; do not add a group/domain split now because it changes the agreed experiment and can materially lower the score.

## 3. Extract lexical features
Implement robust parsing with `urllib.parse.urlsplit`; temporarily prepend `//` only for parsing URLs without a scheme. Produce numeric features only, with no network calls:
- Lengths: URL, hostname, path, query.
- Character counts: `.`, `-`, `_`, `/`, `?`, `=`, `@`, `&`, `%`, digits, and letters.
- Ratios: digit/URL length and special-character/URL length.
- Structure: subdomain count, path depth, query-parameter count, hostname-is-IP, explicit-port flag, percent-encoding flag.
- Raw-ablation only: add HTTPS flag and has-scheme flag, computed on the raw URL.
- Shannon entropy of the complete URL string.

Return columns in one fixed order and assert that the matrix contains no NaN or infinity. Cache feature matrices under `artifacts/` so model and XAI reruns do not repeat extraction.

## 4. Train and compare models
- Logistic Regression baseline: `StandardScaler` in a pipeline, `class_weight='balanced'`, and sufficient `max_iter` for convergence.
- Random Forest: about 300 trees, `n_jobs=-1`, `class_weight='balanced_subsample'`, `min_samples_leaf=5` and `max_depth` ≈ 25 to keep model size and TreeSHAP time manageable, fixed seed.
- XGBoost: multiclass probabilities, histogram tree method, about 400–600 estimators, moderate depth (start at 8), learning rate around 0.1, and 0.8 row/column subsampling. Supply balanced sample weights because multiclass `scale_pos_weight` is not appropriate.
- Fit only on training data. Use validation macro-F1 to select the model and, only if necessary, run a small manual search over tree depth and estimator count. Avoid broad grid search.
- Retrain the chosen configuration on train+validation, evaluate exactly once on test, and save the model, label encoder, ordered feature names, predictions, probabilities, classification report, and confusion matrix.
- If accuracy is below 95%, first inspect per-class confusion and parser/feature bugs. Do not leak test information, remove difficult rows, or tune against the test set merely to reach 95%.

## 5. Verify model behavior
- Unit-test scheme and scheme-less URLs, IP hosts, HTTPS, query parameters, percent encoding, empty paths, and entropy/ratio edge cases.
- Add assertions for deterministic features, mutually exclusive split IDs, valid probability rows, known class mapping, and loading the saved model for inference.
- Create a compact manual test set with representative benign, phishing-like, malware-like, and defacement-like strings. Use it only as a software sanity check, not as evidence of predictive performance.

## 6. Generate SHAP and LIME explanations
- Select 125 correctly processed test instances from each **predicted** class with seed 42; save their row IDs before explaining.
- Explain the same predicted class for both methods and retain signed values plus absolute magnitudes for every feature.
- SHAP: use `TreeExplainer` for the selected RF/XGBoost model. Normalize version-dependent list/2D/3D multiclass outputs into one record per URL and feature for the predicted class; assert dimensions before continuing.
- LIME: use `LimeTabularExplainer` with a fixed random training subsample, fixed feature names/class names, `random_state=42`, default quartile discretization (`discretize_continuous=True`; non-discretized mode would sample around the training mean, not the instance), `num_features` equal to all features, `labels=(predicted_class,)`, read weights via `as_map()`, and initially `num_samples=2000`. Run a 10-URL pilot first to estimate total runtime.
- Warm each explainer before timing. Then time each URL separately with `time.perf_counter()`, sequentially on the same machine, without including model/data loading or disk writing. Save results after each URL so interruption does not lose the run.
- Save raw explanations and timings to `results/shap_explanations.csv`, `results/lime_explanations.csv`, and `results/explanation_times.csv`. Never regenerate them merely to improve findings.

## 7. Compute agreement and statistics
- Rank features by absolute contribution. Break exact ties deterministically by feature name.
- Per URL, calculate top-5 Jaccard similarity and Spearman correlation over the full absolute-importance vectors. Spearman is undefined when a vector is constant; record NaN and report the count. Report mean, median, standard deviation, proportion with Jaccard below 0.50, and (optional) bootstrap 95% confidence interval.
- RQ1/H1: declare project-level “considerable disagreement” only if the overall mean Jaccard is below the pre-fixed 0.50 threshold; also report the full distribution instead of reducing it to one label.
- RQ2: calculate agreement summaries per predicted class and apply Kruskal–Wallis to per-URL Jaccard values. Report the statistic and p-value; avoid claiming which classes differ unless follow-up pairwise tests with multiplicity correction are performed.
- RQ3: compare paired per-URL times using Wilcoxon signed-rank, and report medians, IQRs, p-value, and median speed ratio. State that per-instance TreeSHAP versus perturbation-based LIME is the measured setup, not a universal speed comparison.
- Inspect and tabulate 8–12 cases: highest agreement, lowest agreement, and examples from every class. Do not claim agreement equals explanation correctness.

## 8. Produce report-ready outputs
Generate reproducible figures and CSV tables:
- Class distribution and data-cleaning summary.
- Validation model comparison and final test metrics.
- Raw-URL vs normalized-URL ablation table.
- Normalized and raw confusion matrices.
- Jaccard histogram/boxplot overall and by predicted class.
- SHAP-versus-LIME timing boxplot on a log scale.
- Top global features for each explainer and a small disagreement-case table.

Use only measured values from saved result files in the report. Document exact split policy, preprocessing, hyperparameters, seed, package versions, sample selection, LIME perturbation count, timing protocol, statistical tests, and limitations. Paper 5 (Nair & Di Troia) must be read in full before writing novelty claims (try SJSU ScholarWorks or the library); if still inaccessible, say so and keep claims modest.