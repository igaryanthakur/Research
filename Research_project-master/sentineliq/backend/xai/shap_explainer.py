import logging
from dataclasses import dataclass
from typing import Any, List

logger = logging.getLogger("sentineliq.shap")


@dataclass
class SHAPFeature:
    feature: str
    weight: float
    direction: str  # "positive" or "negative"

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "weight": round(float(self.weight), 6),
            "direction": self.direction,
        }


@dataclass
class TokenScore:
    token: str
    score: float

    def to_dict(self) -> dict:
        return {"token": self.token, "score": round(float(self.score), 4)}


def explain_url(
    model: Any, feature_vector: List[float], feature_names: List[str]
) -> List[dict]:
    """
    Use TreeExplainer on RandomForest / GBT URL model.
    Returns top 5 features sorted by absolute SHAP value as dicts.
    On any failure: returns empty list, logs warning.
    """
    try:
        import shap  # type: ignore[import]
        import numpy as np

        X = np.array([feature_vector], dtype=float)
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        # For binary classifiers shap_values may be shape (1, n_features, 2) or (1, n_features)
        if isinstance(shap_values, list):
            vals = shap_values[1][0]  # class 1 (malicious)
        else:
            vals = shap_values[0]

        features = []
        for i, name in enumerate(feature_names):
            w = float(vals[i])
            features.append(
                SHAPFeature(
                    feature=name.replace("_", " "),
                    weight=round(abs(w), 6),
                    direction="positive" if w >= 0 else "negative",
                )
            )
        top5 = sorted(features, key=lambda f: float(f.weight), reverse=True)[:5]
        return [f.to_dict() for f in top5]
    except Exception as exc:
        logger.warning("explain_url failed (non-fatal): %s", exc)
        return []


def explain_anomaly(
    model: Any, feature_vector: List[float], feature_names: List[str]
) -> List[dict]:
    """
    Use TreeExplainer on IsolationForest model.
    Returns top 5 features sorted by absolute SHAP value as dicts.
    On any failure: returns empty list, logs warning.
    """
    try:
        import shap  # type: ignore[import]
        import numpy as np

        X = np.array([feature_vector], dtype=float)
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        if isinstance(shap_values, list):
            vals = shap_values[0]
        else:
            vals = shap_values[0]

        features = []
        for i, name in enumerate(feature_names):
            w = float(vals[i])
            features.append(
                SHAPFeature(
                    feature=name.replace("_", " "),
                    weight=round(abs(w), 6),
                    direction="positive" if w >= 0 else "negative",
                )
            )
        top5 = sorted(features, key=lambda f: float(f.weight), reverse=True)[:5]
        return [f.to_dict() for f in top5]
    except Exception as exc:
        logger.warning("explain_anomaly failed (non-fatal): %s", exc)
        return []


def explain_text(pipeline: Any, text: str) -> List[dict]:
    """
    Use SHAP pipeline explainer on a HuggingFace text classification pipeline.
    Returns top 8 tokens sorted by absolute score as dicts.
    On any failure: returns empty list, logs warning.
    """
    try:
        import shap  # type: ignore[import]

        truncated = str(text)[:512]
        explainer = shap.Explainer(pipeline)
        shap_values = explainer([truncated])

        # Extract token-level values
        tokens: List[str] = list(shap_values.data[0]) # type: ignore
        values: List[float] = [float(v) for v in shap_values.values[0]] # type: ignore

        token_scores = []
        for tok, val in zip(tokens, values):
            tok_str = str(tok).strip()
            if tok_str and tok_str not in ("[CLS]", "[SEP]", "[PAD]"):
                token_scores.append(
                    TokenScore(token=tok_str, score=round(abs(float(val)), 4))
                )

        top8 = sorted(token_scores, key=lambda t: float(t.score), reverse=True)[:8]
        return [t.to_dict() for t in top8]
    except Exception as exc:
        logger.warning("explain_text failed (non-fatal): %s", exc)
        return []
