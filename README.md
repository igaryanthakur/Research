# Malicious URL Detection with ML and XAI

Four-class URL classification—benign, defacement, malware and phishing—using normalized URL-string features, followed by a quantitative SHAP versus LIME study.

## Current results

| Version | Selected model | Inputs | Test accuracy | Macro-F1 |
|---|---|---:|---:|---:|
| V1 | Random Forest | 24 lexical features | 0.8471 | 0.8269 |
| V2 | XGBoost | 36 selected lexical/structural features | 0.9089 | 0.8863 |
| V3 | XGBoost + LightGBM logistic stack | 48 lexical + 300 character TF-IDF features | **0.9485** | **0.9338** |

V3 is the strongest classifier. The completed SHAP/LIME experiment explains the frozen **V2 XGBoost model**, not the V3 stack:

- 500 URLs, balanced across predicted classes;
- mean top-5 Jaccard: **0.1730**;
- mean full-ranking Spearman: **-0.0101**;
- 95.6% of URLs below the pre-fixed 0.50 agreement threshold;
- LIME mean local fidelity R²: **0.1560**.

This separation is intentional. Exact TreeSHAP applies directly to the single V2 XGBoost model. The V3 winner combines XGBoost and LightGBM through a Logistic Regression meta-model, so explaining one base tree model would not explain the final stacked prediction.

## Project layout

```text
malicious_phish.csv
malicious_url_xai/
├── src/                       # cleaning and V1/V2/V3 feature code
├── tests/                     # 55 tests
├── prepare.py / train.py      # V1
├── prepare_v2.py / train_v2.py
├── explain_v2.py / analyze_v2.py
├── prepare_v3.py / train_v3.py
├── check.py                   # latest-model URL prediction
├── artifacts/                # generated models/features
└── results/                  # saved metrics and XAI outputs
documentation/
├── project_documentation_draft.md
├── project_documentation_draft2.md
├── project_documentation_draft3.md
├── day1_log.txt
├── day2_log.txt
└── day3_log.txt
```

## Setup

From the repository root in Windows PowerShell:

```powershell
cd malicious_url_xai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-lock.txt
```

Always activate `.venv` before running project commands.

## Verify the current project

```powershell
python -m pytest
python train_v3.py verify
```

Expected status:

```text
55 tests passed
Verified: final model reloads and matches saved test probabilities.
```

The saved XGBoost model may print a GPU-to-CPU fallback warning on a machine without a visible GPU. Verification is successful when it exits with code 0 and prints the message above.

## Check one URL

```powershell
python check.py "https://example.com/path"
```

`check.py` selects the latest available model, currently V3, and prints the normalized URL, predicted class and four class probabilities. It does not currently print SHAP/LIME explanations.

## Pipeline commands

### V1 baseline and artifact analysis

```powershell
python prepare.py
python train.py
```

V1 provides the Random Forest baseline, raw-versus-normalized ablation and initial hostname-overlap evidence.

### V2 classifier and SHAP/LIME experiment

```powershell
python prepare_v2.py
python train_v2.py baseline ablation lr rf xgb select final verify

python explain_v2.py
python explain_v2.py --stability
python explain_v2.py --retime
python analyze_v2.py --times explanation_times_retime.csv
```

V2 outputs are under `artifacts/v2/`, `results/v2/` and `results/v2/xai/`.

### V3 classification extension

Historical build sequence:

```powershell
python prepare_v3.py
python train_v3.py ablatesingle ensemble stack select
python train_v3.py final
python train_v3.py verify
```

The final V3 result already exists. Do **not** remove `results/v3/test_metrics.json` or rerun model selection to chase a better test score. For normal use, run only:

```powershell
python train_v3.py verify
```

V3 outputs are under `artifacts/v3/` and `results/v3/`.

## Methodological safeguards

- URLs are normalized by removing a leading scheme and one leading `www.` before feature extraction.
- Normalized URLs with contradictory labels are removed, then duplicates are collapsed.
- V3 reuses the fixed V2 stratified train/validation/test split.
- The character TF-IDF vocabulary is fitted on training URLs only.
- No WHOIS, DNS, page content or network lookups are used.
- Candidate models are selected using validation metrics, not test metrics.
- Seed 42 is used for reproducibility.
- Saved models, predictions and feature order are verified after reload.

## Important limitations

- The same test partition was reported in V1 and V2 before V3 was designed. V3 was evaluated once by its own final stage, but its result is not a fully independent confirmatory estimate.
- Approximately 75.3% of test URLs share a hostname with train+validation.
- V3 accuracy is 0.9683 on seen hostnames and 0.8881 on unseen hostnames.
- Character n-grams may learn repeated campaigns, templates, hostnames or source-specific text.
- The unseen-host group has only 21 defacement URLs.
- Dataset licence and original source composition still require final verification.
- SHAP/LIME agreement measures consistency, not explanation correctness.
- Existing V2 explanations must not be presented as explanations of V3.

## Documentation

- `documentation/project_documentation_draft3.md` — current V3 methodology, results, limitations and report-ready text.
- `documentation/day3_log.txt` — chronological V3 development and verification log.
- `documentation/project_documentation_draft2.md` and `day2_log.txt` — complete V2 classifier and SHAP/LIME record.
