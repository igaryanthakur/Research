# Project Documentation Draft 3 — V3 Classification Extension

> **Project:** Detection of Malicious URLs Using Machine Learning and Explainable AI
> **Version documented:** V3 classification pipeline, 10 Nov 2026
> **Current status:** V1/V2/V3 classification complete; V2 SHAP/LIME experiment complete; V3 artifact verification complete
> **Evidence rule:** Every numerical result below comes from saved files under `malicious_url_xai/results/`, `results/v2/`, `results/v2/xai/`, or `results/v3/`.
> **Important boundary:** V3 is the strongest classifier. The existing SHAP/LIME results explain the V2 XGBoost classifier, not the V3 stack.

---

## 1. Executive summary

The project detects four URL classes—benign, defacement, malware and phishing—using URL-string information only. It does not visit websites or use WHOIS, DNS, page content or network traffic.

Three classifier iterations have been completed:

| Version | Main model | Inputs | Test accuracy | Test macro-F1 |
|---|---|---:|---:|---:|
| V1 | Random Forest | 24 normalized lexical features | 0.8471 | 0.8269 |
| V2 | XGBoost | 36 selected lexical/structural features | 0.9089 | 0.8863 |
| V3 | XGBoost + LightGBM logistic stack | 48 lexical + 300 character TF-IDF features | **0.9485** | **0.9338** |

V3 improves every reported class metric over V2. Phishing remains the hardest class, but its F1 rises from 0.7504 to 0.8304. V3 unseen-host accuracy is 0.8881, compared with 0.9683 on seen hostnames, so hostname and campaign overlap remain important limitations.

The completed explanation experiment remains attached to V2 because V2 is one XGBoost model with 36 interpretable features and supports exact TreeSHAP. V3 is a two-base-model stack with 300 correlated character n-gram features. TreeSHAP cannot directly explain the complete stack, and independently perturbing its n-gram columns with LIME Tabular can create unrealistic feature combinations.

---

## 2. Research objective and current contribution

The project asks:

1. How well do SHAP and LIME agree on the most influential features for the same URL predictions?
2. Does agreement differ across predicted URL classes?
3. How do SHAP and LIME differ in per-prediction explanation time?

The completed work supports four contributions:

1. **Dataset artifact audit:** URL scheme and `www` formatting strongly encode collection source; normalization exposes 4,047 contradictory benign/phishing URLs.
2. **Defensible normalized classifier:** V2 reaches 90.89% accuracy without known explicit scheme/HTTPS/`www` features.
3. **Quantitative XAI comparison:** on the V2 model, mean top-5 SHAP/LIME Jaccard is 0.1730 and mean full-ranking Spearman correlation is -0.0101.
4. **V3 classification extension:** character n-grams and boosted-tree stacking raise held-out random-split accuracy to 94.85% and macro-F1 to 0.9338.

The V2-to-V3 increase is an engineering improvement, not by itself the main research novelty. The artifact analysis and controlled SHAP/LIME comparison remain the stronger research story.

---

## 3. Dataset and frozen split

| Property | Value |
|---|---:|
| Raw rows | 651,191 |
| Clean normalized rows | 631,179 |
| Classes | benign, defacement, malware, phishing |
| Train rows | 441,825 |
| Validation rows | 94,677 |
| Test rows | 94,677 |
| Split seed | 42 |

V3 reuses `artifacts/v2/clean.parquet` and the exact V2 train/validation/test assignments. It does not reclean, relabel or resplit the dataset.

Cleaning performed before V2/V3:

1. strip surrounding whitespace;
2. remove one leading scheme and one leading `www.`;
3. remove every normalized URL carrying conflicting labels;
4. keep one row per remaining normalized URL;
5. retain the fixed stratified 70/15/15 split.

The normalization decision remains essential. In the raw dataset, a scheme appears in 8.3% of benign URLs, 100% of defacement URLs, 96.3% of malware URLs and 26.4% of phishing URLs. A V1 ablation showed that raw formatting alone raised accuracy from 84.71% to 94.02%, while explicit scheme flags raised it to 94.66%.

---

## 4. V3 feature engineering

### 4.1 Feature composition

V3 generates 348 features:

| Block | Count | Description |
|---|---:|---|
| V2 generated lexical features | 39 | V1, structural and lexicon fields |
| Segment entropy | 4 | host, path, query entropy and host/path difference |
| Brand signals | 5 | edit distance, typo, subdomain, path/query and exact-host indicators |
| Character TF-IDF | 300 | train-fitted character 3-grams and 4-grams |
| **Total** | **348** | |

Unlike the V2 selected model, which uses 36 of its 39 generated fields, the V3 lexical block includes all 39 V2 generated fields before adding the nine new lexical fields.

### 4.2 Segment entropy

New entropy fields:

- `host_entropy`
- `path_entropy`
- `query_entropy`
- `entropy_host_path_absdiff`

These separate randomness in different URL components instead of using only whole-URL entropy.

### 4.3 Brand and typosquat signals

New fields:

- `min_brand_edit_distance`
- `brand_typo_flag`
- `brand_in_subdomain`
- `brand_in_path_or_query`
- `is_exact_brand_host`

The implementation uses a curated brand list and a best-effort second-level hostname label. It is not Public Suffix List aware. For domains such as `example.co.uk`, the registered-domain approximation may be wrong; this must be reported as a limitation rather than described as exact registered-domain extraction.

### 4.4 Character n-grams

The vectorizer configuration is:

```text
analyzer       = character
ngram range    = (3, 4)
maximum fields = 300
minimum df     = 5
lowercase      = true
sublinear TF   = true
fit data       = training split only
```

Fitting the vocabulary only on training data prevents validation/test vocabulary leakage. Character n-grams capture fragments such as TLDs, path tokens and repeated URL patterns.

They also introduce a threat to validity: n-grams may learn campaign, template, hostname or collection-source fragments. They are lexical inputs, but “lexical” does not automatically mean free of dataset-specific memorization.

### 4.5 Preparation results

From `results/v3/data_audit.json`:

| Item | Value |
|---|---:|
| Lexical fields | 48 |
| Character n-gram fields | 300 |
| Full feature count | 348 |
| Constant new lexical fields | 0 |
| Lexical extraction | 56.5 s |
| N-gram fitting | 24.6 s |
| N-gram transformation | 22.4 s |
| Peak process memory | 3,213.1 MB |

---

## 5. V3 models

V3 evaluates boosted-tree families and ensembles:

- XGBoost
- LightGBM
- CatBoost
- equal-probability soft voting
- out-of-fold Logistic Regression stacking

Random Forest is not a V3 candidate. It remains the V1 winner and was evaluated in V2, where XGBoost outperformed it. The V3 report must not imply that Random Forest was trained again on the 348-feature representation.

### 5.1 Base configurations

**XGBoost**

```text
max_depth        10
learning_rate    0.1
subsample        0.8
colsample_bytree 0.8
maximum rounds   1,200
early stopping   50
weighting        square-root balanced
```

**LightGBM**

```text
num_leaves       128
learning_rate    0.05
subsample        0.8
colsample_bytree 0.8
min_child_samples 40
maximum rounds   2,000
early stopping   50
weighting        square-root balanced
```

**CatBoost**

```text
depth            8
learning_rate    0.08
l2_leaf_reg      3.0
maximum rounds   800
early stopping   40
weighting        square-root balanced
```

### 5.2 Stack architecture

The selected stack is:

```text
348-feature URL vector
    ├── XGBoost ──> four class probabilities
    └── LightGBM ─> four class probabilities
                         │
                         ▼
              Logistic Regression meta-model
                         │
                         ▼
                 final four-class prediction
```

Three-fold stratified out-of-fold predictions train the Logistic Regression meta-model without using each row’s in-fold base prediction. For final evaluation, the stack is rebuilt on train+validation and predicts the test partition.

---

## 6. Validation results and selection

| Trial | Features | Accuracy | Macro-F1 | Phishing recall | Unseen-host accuracy |
|---|---:|---:|---:|---:|---:|
| V2-reference XGBoost | 39 | 0.9085 | 0.8855 | 0.7517 | 0.8332 |
| V3 lexical XGBoost | 48 | 0.9216 | 0.9010 | 0.7633 | 0.8446 |
| V3 full XGBoost | 348 | 0.9445 | 0.9291 | 0.8133 | 0.8765 |
| V3 full LightGBM | 348 | 0.9448 | 0.9298 | 0.8116 | 0.8756 |
| V3 full CatBoost | 348 | 0.9146 | 0.8944 | 0.7819 | 0.8487 |
| XGB + LGBM soft vote | 348 | 0.9458 | **0.9309** | **0.8132** | 0.8776 |
| XGB + LGBM LR stack | 348 | **0.9463** | 0.9307 | 0.7961 | **0.8796** |

Selection rule:

1. highest validation macro-F1;
2. candidates within 0.005 are near-tied;
3. among near ties, choose higher accuracy;
4. then higher minimum malicious-class recall;
5. then lower fitting time;
6. select from the full V3 feature pool.

The soft vote has slightly higher macro-F1 and phishing recall, but both ensembles are inside the 0.005 tie range. The stack wins on validation accuracy, 0.9463 versus 0.9458.

This trade-off must be stated. The selection rule—not a claim that the stack dominates every metric—determines the winner.

---

## 7. V3 held-out test results

### 7.1 Aggregate results

| Metric | V3 |
|---|---:|
| Accuracy | **0.9485** |
| Macro precision | 0.9444 |
| Macro recall | 0.9239 |
| Macro-F1 | **0.9338** |
| Weighted-F1 | 0.9480 |

### 7.2 Per-class results

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Benign | 0.9581 | 0.9715 | 0.9648 | 63,472 |
| Defacement | 0.9808 | 0.9806 | 0.9807 | 14,296 |
| Malware | 0.9851 | 0.9350 | 0.9594 | 3,539 |
| Phishing | 0.8537 | 0.8085 | 0.8304 | 13,370 |

### 7.3 Confusion matrix

Rows are true classes and columns are predicted classes.

| True \ Predicted | Benign | Defacement | Malware | Phishing |
|---|---:|---:|---:|---:|
| Benign | 61,665 | 181 | 11 | 1,615 |
| Defacement | 184 | 14,018 | 4 | 90 |
| Malware | 79 | 3 | 3,309 | 148 |
| Phishing | 2,436 | 90 | 35 | 10,809 |

The largest remaining error is phishing predicted as benign: 2,436 URLs.

### 7.4 Model artifact

| Property | Value |
|---|---:|
| Final family | Logistic stack over XGBoost + LightGBM |
| Input fields | 348 |
| Final fitting data | train + validation |
| Final fitting time | 1,916.3 s |
| Saved model size | 111.0 MB |
| Peak process memory | 5,196.5 MB |

---

## 8. V2 versus V3

| Metric | V2 | V3 | Change |
|---|---:|---:|---:|
| Accuracy | 0.9089 | **0.9485** | +0.0396 |
| Macro-F1 | 0.8863 | **0.9338** | +0.0475 |
| Benign recall | 0.9345 | **0.9715** | +0.0370 |
| Defacement recall | 0.9395 | **0.9806** | +0.0411 |
| Malware recall | 0.9053 | **0.9350** | +0.0297 |
| Phishing recall | 0.7559 | **0.8085** | +0.0526 |
| Phishing precision | 0.7451 | **0.8537** | +0.1086 |
| Phishing F1 | 0.7504 | **0.8304** | +0.0800 |

V3 improves all displayed test metrics. This is larger than a minor model-tuning gain: most of the validation increase appears when adding the 300 character n-grams, with a smaller ensemble gain afterward.

The comparison does not prove future-domain performance. It uses the same random URL-level split and dataset as earlier versions.

---

## 9. Hostname-overlap analysis

| Subgroup | n | Accuracy | Macro-F1 | Benign R | Defacement R | Malware R | Phishing R |
|---|---:|---:|---:|---:|---:|---:|---:|
| All test | 94,677 | 0.9485 | 0.9338 | 0.9715 | 0.9806 | 0.9350 | 0.8085 |
| Seen hostname | 71,276 | 0.9683 | 0.9499 | 0.9825 | 0.9807 | 0.9791 | 0.8330 |
| Unseen hostname | 23,401 | 0.8881 | 0.6907 | 0.9380 | 0.8571* | 0.7979 | 0.7850 |

`*` The unseen-host test group contains only 21 defacement URLs, so its defacement recall and macro-F1 are unstable.

Compared with V2, unseen-host accuracy rises from 0.8357 to 0.8881 and macro-F1 from 0.6311 to 0.6907. This provides evidence that V3 improves beyond familiar hostnames, but the large seen/unseen gap remains.

---

## 10. Test-set protocol caveat

Within the V3 script:

- features and vocabulary are fitted on training data;
- candidate comparison and winner selection use validation data;
- the V3 final stage evaluates the selected winner once;
- the final stage refuses to overwrite an existing V3 test result.

However, the same fixed test partition had already been evaluated for V1 and V2 before V3 was designed. V3 development was motivated partly by the observed earlier results. Therefore, the project must not describe the V3 test partition as globally untouched.

Defensible wording:

> V3 was selected using the fixed validation partition and evaluated once by the V3 final stage on the held-out random-split test partition. Because the same test partition had been reported for earlier project iterations, the V3 score is not a fully independent confirmatory estimate.

Avoid:

> V3 was evaluated on a completely untouched test set.

No further feature or model tuning should use these test results.

---

## 11. Reproducibility, testing and verification

### 11.1 Saved V3 files

```text
malicious_url_xai/
├── src/features_v3.py
├── tests/test_features_v3.py
├── prepare_v3.py
├── train_v3.py
├── artifacts/v3/
│   ├── clean.parquet
│   ├── features_v3_lexical.parquet
│   ├── features_v3_ngram.parquet
│   ├── features_v3_full.parquet
│   ├── ngram_vectorizer.joblib
│   ├── feature_manifest.json
│   ├── final_model.joblib
│   ├── label_encoder.joblib
│   ├── feature_names.json
│   └── selected_config.json
└── results/v3/
    ├── data_audit.json
    ├── model_trials_val.csv
    ├── model_trials_ranked_val.csv
    ├── selection.json
    ├── test_metrics.json
    ├── classification_report.txt
    ├── classification_report.csv
    ├── confusion_matrix.csv
    ├── confusion_matrix_normalized.csv
    ├── test_predictions.csv
    ├── hostname_subgroup_test.csv
    ├── v2_vs_v3.csv
    └── run_metadata.json
```

### 11.2 Tests

On 10 Nov 2026, the complete suite was rerun under Python 3.13.14:

```text
55 tests passed in 1.99 seconds
```

Breakdown:

- 12 V1 feature/data tests;
- 23 V2 feature tests;
- 15 V3 feature tests;
- 5 V2 pipeline smoke tests.

Current gap: there is no dedicated automated V3 stack serialization/checker test file. The runtime verification below covers the saved final stack, but a future code-quality pass could add focused tests.

### 11.3 Final artifact verification

`python train_v3.py verify`:

1. reloads the final model bundle and label encoder;
2. reads the first 2,000 saved test predictions;
3. selects the matching feature rows using saved `row_id` values;
4. rebuilds XGBoost and LightGBM probabilities;
5. applies the Logistic Regression meta-model;
6. checks finite probabilities summing to one;
7. verifies equality with saved test probabilities within tolerance.

Verified output:

```text
Verified: final model reloads and matches saved test probabilities.
```

The model was trained with GPU-enabled XGBoost but successfully reloads and predicts on CPU. XGBoost prints a device-fallback warning when no GPU is available; verification still passes.

### 11.4 Environment

Saved V3 run metadata:

| Package | Version |
|---|---|
| Python | 3.13.5 |
| NumPy | 2.2.6 |
| pandas | 2.3.3 |
| scikit-learn | 1.7.2 |
| XGBoost | 3.2.0 |
| LightGBM | 4.7.0 |
| CatBoost | 1.2.10 |

The full pinned environment is in `requirements-lock.txt`. The later verification and test run used the project virtual environment under Python 3.13.14.

---

## 12. Relationship between V3 and the SHAP/LIME experiment

### 12.1 Completed V2 XAI result

The frozen V2 XGBoost model uses 36 human-readable fields and supports exact path-dependent TreeSHAP.

On 500 class-balanced saved predictions:

| Result | Value |
|---|---:|
| Mean top-5 Jaccard | 0.1730 |
| Bootstrap 95% CI | 0.1571–0.1889 |
| Share below 0.50 | 95.6% |
| Mean full-ranking Spearman | -0.0101 |
| LIME mean local R² | 0.1560 |
| TreeSHAP median time | 224.19 ms |
| LIME median time | 60.85 ms |

These results remain valid for V2.

### 12.2 Why they cannot be relabelled as V3 explanations

The V3 final prediction is generated by two tree models followed by a Logistic Regression meta-model. Exact TreeSHAP can explain an individual XGBoost or LightGBM base model, but not the complete stacked decision through one direct tree-explainer call.

Explaining only one base model would not explain V3’s final prediction. Model-agnostic SHAP is theoretically possible but substantially more expensive over 348 fields and 500 URLs.

LIME can call the full stack as a black box, but independently perturbing 300 correlated TF-IDF n-gram fields can produce vectors that do not correspond to real URLs. The already low V2 LIME fidelity also warns against assuming that a higher-dimensional V3 surrogate would be reliable.

### 12.3 Current reporting options

**Lowest-risk option for the current deadline**

- report V3 as the final classification model;
- report V2 as the explicitly named explanation model;
- never imply that V2 SHAP/LIME values explain V3.

**Alternative requiring more work**

- designate a single V3 XGBoost or LightGBM model as the explanation target;
- explain that single model only;
- accept that it is not the selected final stack.

The choice should be made before finalizing the report wording. The current saved evidence supports the first option with the least additional risk.

---

## 13. Limitations and threats to validity

1. **Single dataset:** results may not transfer to current URLs or another source.
2. **Test reuse across iterations:** V3 is not a fully independent confirmatory test.
3. **Random URL-level split:** 75.3% of test URLs share a hostname with train+validation.
4. **N-gram memorization:** character fragments may encode campaigns, templates, hostnames or source artifacts.
5. **Unseen-host imbalance:** only 21 unseen-host defacement URLs are available.
6. **Label quality:** normalization removed known contradictions, but residual errors may remain.
7. **Lexical-only input:** no content, registration, DNS or network evidence is used.
8. **Brand parser approximation:** second-level-label extraction is not Public Suffix List aware.
9. **Bounded model search:** the tested configurations do not establish globally optimal algorithms.
10. **Random Forest absent from V3:** V3 comparisons are among boosted trees and ensembles only.
11. **XAI/model separation:** the completed SHAP/LIME evidence explains V2, not the V3 stack.
12. **Agreement is not correctness:** neither SHAP nor LIME supplies explanation ground truth.
13. **LIME fidelity:** V2 mean local R² is only 0.156.
14. **Timing specificity:** V2 timing compares all-class TreeSHAP against predicted-class LIME.
15. **Dataset licence/provenance:** final source and licence verification remains open.

---

## 14. Commands

From `malicious_url_xai/`:

```powershell
.\.venv\Scripts\Activate.ps1

# Quality checks
python -m pytest
python train_v3.py verify

# Historical V3 build sequence; do not rerun final while saved results exist
python prepare_v3.py
python train_v3.py ablatesingle ensemble stack select
python train_v3.py final
python train_v3.py verify

# Current single-URL prediction
python check.py "https://example.com/path"

# Completed V2 explanation pipeline
python explain_v2.py
python explain_v2.py --stability
python explain_v2.py --retime
python analyze_v2.py --times explanation_times_retime.csv
```

The existing `results/v3/test_metrics.json` protects against accidental rerunning of the V3 final stage.

---

## 15. Reusable report text

### 15.1 V3 methodology

> V3 retained the fixed normalized dataset and train/validation/test assignments from V2. Nine segmented-entropy and brand-related lexical fields were added to the 39 generated V2 fields. A character-level TF-IDF vocabulary of 300 three- and four-character n-grams was fitted only on the training partition, producing 348 total inputs. Square-root-balanced XGBoost, LightGBM and CatBoost classifiers were evaluated on validation data, followed by probability averaging and a three-fold out-of-fold Logistic Regression stack. The pre-fixed near-tie rule selected the XGBoost-LightGBM stack because its macro-F1 was within 0.005 of the best candidate and it had the highest validation accuracy.

### 15.2 V3 result

> The selected V3 stack achieved 94.85% accuracy and macro-F1 0.9338 on the held-out random-split test partition. Class F1 scores were 0.9648 for benign, 0.9807 for defacement, 0.9594 for malware and 0.8304 for phishing. Relative to V2, accuracy increased by 3.96 percentage points and macro-F1 by 0.0475, while phishing precision, recall and F1 all improved.

### 15.3 Generalization caveat

> Of the 94,677 test URLs, 71,276 shared a hostname with train+validation data. V3 accuracy was 96.83% on seen hostnames and 88.81% on unseen hostnames. The unseen-host macro-F1 of 0.6907 is affected by having only 21 unseen-host defacement URLs. Character n-grams may also encode repeated campaigns and templates. The headline score therefore should not be interpreted as performance on entirely new websites or data sources.

### 15.4 Test-reuse caveat

> Candidate selection within V3 used validation data and the selected V3 pipeline was evaluated once by its final stage. However, the fixed test partition had already been reported for V1 and V2 before V3 was designed. The V3 test result is therefore held out from direct fitting but is not a fully independent confirmatory estimate.

### 15.5 Classification/XAI boundary

> V3 is reported as the strongest classification model. The controlled SHAP/LIME experiment uses the frozen V2 XGBoost classifier because its 36 human-readable features support exact TreeSHAP and a direct same-model comparison with LIME. The V2 explanation values are not presented as explanations of the V3 stacked classifier.

---

## 16. Recommended paper and presentation story

1. Introduce the malicious-URL and explanation-trust problem.
2. Show the scheme/`www` dataset artifact and contradictory-label finding.
3. Present V1 and V2 as the defensible normalized modelling pipeline.
4. Present the completed V2 SHAP/LIME disagreement, fidelity and timing evidence.
5. Present V3 as a later classification extension showing the gain from character n-grams and stacking.
6. Discuss the accuracy–interpretability trade-off: the strongest stack is harder to explain faithfully.
7. Close with hostname overlap, test reuse, n-gram memorization and external-validation limitations.

This ordering keeps the research contribution centered on evidence rather than treating model accuracy as the only result.

---

## 17. Current completion status

### Completed

- V1 baseline and raw-format artifact ablation.
- V2 structural feature ablation and LR/RF/XGBoost comparison.
- Frozen V2 XGBoost classifier.
- V2 SHAP/LIME agreement, class comparison, fidelity, stability and timing.
- V3 entropy/brand and character n-gram feature generation.
- V3 XGBoost, LightGBM and CatBoost validation trials.
- V3 soft-voting and out-of-fold stacking trials.
- V3 final held-out evaluation and V2 comparison.
- V3 seen/unseen hostname analysis.
- V3 model reload and saved-probability verification.
- Complete test suite: 55 passing.

### Open

- Decide final wording for the V2-XAI/V3-classifier separation.
- Create a V3 checksum freeze manifest.
- Update the final report, references and presentation slides.
- Verify the dataset licence and original source composition.
- Read and position the closest SHAP/LIME paper in full.
- Verify venue indexing.
- Optionally add focused automated tests for V3 stack serialization and `check.py`.
- Build the viva demonstration after the report is stable.
