import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from src.data import CLASSES, SEED
from src.features_v2 import FEATURE_NAMES_V2, build_feature_frame_v2
from train_v2 import class_weights, eligibility, evaluate, fit_rf, fit_xgb, order_by_rule

URLS = {
    "benign": ["google.com/search?q=cats", "en.wikipedia.org/wiki/Cat", "github.com/user/repo"],
    "defacement": ["site.com.br/index.php?option=com_content&catid=26:x", "abc.de/index.php?view=article"],
    "malware": ["42.225.234.216:33101/Mozi.m", "1.2.3.4:8080/bin.sh"],
    "phishing": ["paypal.com.secure-update.xyz/login", "bit.ly/verify-account", "a.tk/signin//http://b.com"],
}


def synthetic():
    rows = [(u + f"/{i}", c) for c, urls in URLS.items() for u in urls for i in range(15)]
    urls, labels = zip(*rows)
    enc = LabelEncoder().fit(CLASSES)
    return build_feature_frame_v2(urls), enc.transform(labels), enc


def test_class_weights_modes():
    y = np.array([0] * 70 + [1] * 10 + [2] * 10 + [3] * 10)
    assert class_weights(y, "none") is None
    bal, sq = class_weights(y, "balanced"), class_weights(y, "sqrt_balanced")
    assert np.isclose(bal[0], 100 / (4 * 70)) and np.isclose(bal[1], 100 / (4 * 10))
    assert all(np.isclose(sq[k], bal[k] ** 0.5) for k in bal)


def test_order_by_rule_tie_prefers_accuracy():
    df = pd.DataFrame({"macro_f1": [0.830, 0.827, 0.810], "accuracy": [0.85, 0.87, 0.90],
                       "recall_defacement": [0.9] * 3, "recall_malware": [0.9] * 3,
                       "recall_phishing": [0.8] * 3, "fit_s": [1, 1, 1]}, index=["a", "b", "c"])
    assert list(order_by_rule(df).index) == ["b", "a", "c"]


def test_eligibility_gate():
    good = {"accuracy": 0.86, "macro_f1": 0.83, "recall_defacement": 0.88,
            "recall_malware": 0.87, "recall_phishing": 0.78}
    assert eligibility(good)[0]
    assert not eligibility({**good, "accuracy": 0.846})[0]
    assert not eligibility({**good, "recall_phishing": 0.69})[0]
    assert not eligibility({**good, "recall_phishing": 0.74})[0]
    assert eligibility({**good, "recall_phishing": 0.74, "macro_f1": 0.84})[0]


def test_chunked_rf_equals_single_fit():
    X, y, _ = synthetic()
    params = {"n_estimators": 120, "max_depth": None, "min_samples_leaf": 1, "max_features": "sqrt"}
    chunked, extra = fit_rf(X, y, params, None)
    single = RandomForestClassifier(n_estimators=120, bootstrap=True, n_jobs=-1, random_state=SEED,
                                    max_features="sqrt").fit(X, y)
    assert extra["n_estimators_used"] == 120
    np.testing.assert_allclose(chunked.predict_proba(X), single.predict_proba(X))


def test_artifacts_roundtrip_and_probabilities(tmp_path):
    X, y, enc = synthetic()
    assert list(X.columns) == FEATURE_NAMES_V2
    for model in (fit_rf(X, y, {"n_estimators": 50, "max_depth": 25, "min_samples_leaf": 1,
                                "max_features": "sqrt"}, class_weights(y, "sqrt_balanced"))[0],
                  fit_xgb(X, y, {"max_depth": 3, "learning_rate": 0.1}, None, n_estimators=20)[0]):
        joblib.dump(model, tmp_path / "m.joblib")
        joblib.dump(enc, tmp_path / "e.joblib")
        (tmp_path / "f.json").write_text(json.dumps(list(X.columns)))
        m, e = joblib.load(tmp_path / "m.joblib"), joblib.load(tmp_path / "e.joblib")
        cols = json.loads((tmp_path / "f.json").read_text())
        proba = m.predict_proba(X[cols])
        assert proba.shape == (len(X), 4) and np.isfinite(proba).all()
        assert np.allclose(proba.sum(axis=1), 1, atol=1e-5)
        assert list(e.classes_) == CLASSES and list(m.classes_) == [0, 1, 2, 3]
        assert evaluate(y, proba.argmax(axis=1))["accuracy"] > 0.5
