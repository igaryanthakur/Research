# Malicious URL Detection with ML and XAI (SHAP vs LIME)

Four-class lexical URL classifier (benign, defacement, malware, phishing) on `../malicious_phish.csv`,
followed by a SHAP vs LIME agreement and latency comparison.

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-lock.txt
```

## Check one URL

From this folder, with the virtual environment active:

```powershell
python check.py "https://example.com/path"
```

Prints the normalized URL, the predicted class, and the score for each class.

## Run order

```powershell
pytest                 # feature/cleaning sanity tests
python prepare.py      # clean, split 70/15/15, cache features -> artifacts/, results/data_audit.json
python train.py        # LR vs RF vs XGBoost, final test metrics, 3-way raw-URL ablation,
                       # seen/unseen hostname subgroups -> results/
python explain.py      # (next) SHAP + LIME on a fixed 500-URL sample
python analyze.py      # (next) agreement, statistical tests, figures
```

## Fixed protocol

- Seed 42 everywhere. Stratified 70/15/15 split; test set used once.
- URLs are normalized (scheme and leading `www.` removed) before feature extraction, because in this
  dataset scheme/`www.` presence depends on the source of each class. `train.py` reports the effect of
  skipping this step (`results/ablation_raw_vs_normalized.csv`).
- Model selected by validation macro-F1.
- XAI: k = 5, 500 test URLs (125 per predicted class), considerable disagreement = mean top-5 Jaccard < 0.50.
