# Malicious URL Detection with ML and XAI

Four-class URL classification (benign, defacement, malware, phishing) from the text of the URL alone, with a study of how well SHAP and LIME agree when explaining the classifier.

The repository serves two outputs:

- **Sem 3 research project:** the V3 classifier, a small web app that classifies a URL and shows which parts of it drove the result, and the report.
- **Sem 4 research paper:** a short paper on SHAP vs LIME agreement and cost for malicious-URL classification.

## Current results

| Version | Role | Model | Inputs | Test accuracy | Macro-F1 |
|---|---|---|---:|---:|---:|
| V1 | Baseline; proves the dataset leakage | Random Forest | 24 lexical features | 0.8471 | 0.8269 |
| V2 | Intermediate; preliminary SHAP/LIME study | XGBoost | 36 lexical/structural features | 0.9089 | 0.8863 |
| V3 | **Final model** | XGBoost + LightGBM logistic stack | 48 lexical + 300 character TF-IDF features | **0.9485** | **0.9338** |

V3 is final and frozen at 94.85%. No further training or tuning is planned.

## Status and direction

Done:

- V1, V2 and V3 classifiers, with saved metrics and predictions.
- Dataset leakage analysis: URL scheme and `www.` formatting reveal the class; removing them lowers the V1 baseline from 94.02% to 84.71% and exposes 4,047 contradictory labels.
- Preliminary SHAP vs LIME study on the frozen **V2** XGBoost model (500 URLs, top-5 of 36 features):
  - mean top-5 Jaccard **0.1730**; 95.6% of URLs below the pre-fixed 0.50 threshold;
  - mean full-ranking Spearman **-0.0101**;
  - LIME mean local R² **0.1560**.

Not done yet:

- The main experiment: SHAP vs LIME on the **V3 stack**, using URL-segment masking with all 348 features recomputed for each perturbed URL.
- The web app.
- The final report and slides.

The V2 explanation results describe V2 only. They must not be presented as explanations of V3.

Next stages, in order:

1. Add a shuffled null baseline to the saved V2 explanation results.
2. Freeze V3 with a checksum manifest.
3. Write and approve the V3 experiment protocol.
4. Build the segment explainer and run a 20-URL pilot (5 per predicted class).
5. Run the full V3 experiment and analysis.
6. Build the Streamlit web app.
7. Write the report and slides.

`documentation/project_documentation_draft4.md` holds the full plan, the proposal draft and a plain-English guide.

## Project layout

```text
malicious_phish.csv            # Kaggle dataset, 651,191 URLs
RSPJ4.txt                      # current project context prompt
RSPJ.txt                       # original pre-project plan (superseded)
malicious_url_xai/
├── src/                       # cleaning and V1/V2/V3 feature code
├── tests/                     # 55 tests
├── prepare.py / train.py      # V1
├── prepare_v2.py / train_v2.py
├── explain_v2.py / analyze_v2.py
├── prepare_v3.py / train_v3.py
├── check.py                   # latest-model URL prediction
├── artifacts/                 # generated models/features (not in git)
└── results/                   # saved metrics and XAI outputs
documentation/
├── project_documentation_draft.md    # V1 record
├── project_documentation_draft2.md   # V2 and V2 SHAP/LIME record
├── project_documentation_draft3.md   # V3 record
├── project_documentation_draft4.md   # current direction and roadmap
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

Expected status (last confirmed 14 Nov 2026):

```text
55 passed
Verified: final model reloads and matches saved test probabilities.
```

The saved XGBoost model prints a GPU-to-CPU fallback warning on a machine without a visible GPU. Verification is successful when it exits with code 0 and prints the message above.

## Check one URL

```powershell
python check.py "https://example.com/path"
```

`check.py` selects the latest available model, currently V3, and prints the normalized URL, predicted class and four class probabilities. It does not yet print explanations.

Known behaviour: the model misjudges some everyday URLs. On 14 Nov 2026 it labelled `https://www.google.com` as phishing (88%) and an obviously fake PayPal URL as benign (91%). In the dataset, short bare-domain URLs are mostly phishing, and the model learned that pattern. Treat the tool as a research demonstration, not a security product.

## Pipeline commands

### V1 baseline and leakage analysis

```powershell
python prepare.py
python train.py
```

V1 provides the Random Forest baseline, the raw-versus-normalized ablation and the first hostname-overlap evidence.

### V2 classifier and preliminary SHAP/LIME study

```powershell
python prepare_v2.py
python train_v2.py baseline ablation lr rf xgb select final verify

python explain_v2.py
python explain_v2.py --stability
python explain_v2.py --retime
python analyze_v2.py --times explanation_times_retime.csv
```

V2 outputs are under `artifacts/v2/`, `results/v2/` and `results/v2/xai/`.

### V3 final classifier

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
- The model reflects the dataset's habits; well-known short URLs can be misclassified.
- SHAP/LIME agreement measures consistency, not explanation correctness.
- Only one dataset is used; there is no external validation.

## Documentation

- `documentation/project_documentation_draft4.md` — start here: idea, proposal draft, current status, next stages and a plain-English guide.
- `documentation/project_documentation_draft3.md` and `day3_log.txt` — V3 methodology, results and development log.
- `documentation/project_documentation_draft2.md` and `day2_log.txt` — V2 classifier and the preliminary SHAP/LIME record.
- `documentation/project_documentation_draft.md` and `day1_log.txt` — V1 baseline and the leakage finding.
