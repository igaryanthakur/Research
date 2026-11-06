"""
engines/anomaly.py — Behavioural Anomaly Detector
===================================================

IsolationForest trained on role-specific synthetic baselines.
Feature list, contamination, seed, and thresholds come from config.py.

Never crashes — all exceptions return a safe heuristic fallback.
"""

import os
import asyncio
import logging
import json
import math
import numpy as np  # type: ignore[import]
from typing import Any, Dict, List, Optional
from fastapi import FastAPI  # type: ignore[import-untyped]

logger = logging.getLogger("sentineliq.anomaly")

from config import AnomalyConfig  # type: ignore[import]

_is_serverless = os.getenv("VERCEL") == "1" or os.getenv("RENDER") == "true"
_db_dir = "/tmp" if _is_serverless else os.path.join(os.path.dirname(__file__), "..", "db")

JOBLIB_PATH_TEMPLATE  = os.path.join(_db_dir, "anomaly_model_{role}.joblib")
BASELINE_PATH_TEMPLATE = os.path.join(_db_dir, "baseline_data_{role}.json")

_ROLES = ["developer", "executive", "standard"]

# Convenience shortcuts loaded from config (so no hardcoding below)
FEATURE_NAMES: List[str] = AnomalyConfig.FEATURE_NAMES
DEFAULTS:      Dict[str, float] = AnomalyConfig.DEFAULTS


# ─── Sigmoid calibration ──────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    """
    Maps IsolationForest decision_function to [0, 1] probability of anomaly.
    decision_function > 0 (normal)  → probability close to 0
    decision_function < 0 (anomaly) → probability close to 1
    """
    k = AnomalyConfig.SIGMOID_K
    try:
        return 1.0 / (1.0 + math.exp(x * k))
    except OverflowError:
        return 0.0 if x > 0 else 1.0


# ─── Input validation ─────────────────────────────────────────────────────────

def _validate_and_build_vector(
    session_data: Dict[str, Any],
    baseline_means: Optional[Dict[str, float]] = None,
) -> List[float]:
    """
    Build feature vector from session dict.
    - Missing values → DEFAULTS
    - NaN / None → replaced with feature mean (or DEFAULTS if no mean available)
    - Wrong type  → cast to float gracefully
    Raises ValueError if vector length != len(FEATURE_NAMES).
    """
    vec: List[float] = []
    for feat in FEATURE_NAMES:
        raw = session_data.get(feat, DEFAULTS[feat])
        # NaN / None guard
        if raw is None:
            raw = baseline_means.get(feat, DEFAULTS[feat]) if isinstance(baseline_means, dict) else DEFAULTS[feat]
        try:
            if raw is None:
                val = float(DEFAULTS[feat])
            else:
                val = float(str(raw))
            if not math.isfinite(val):
                b_val = baseline_means.get(feat, DEFAULTS[feat]) if baseline_means else DEFAULTS[feat]
                val = float(str(b_val))
        except (TypeError, ValueError):
            val = DEFAULTS[feat]
        vec.append(val)

    if len(vec) != len(FEATURE_NAMES):
        raise ValueError(f"Feature vector length mismatch: {len(vec)} != {len(FEATURE_NAMES)}")
    return vec


# ─── Baseline generation ──────────────────────────────────────────────────────

def _generate_baseline(role: str) -> List[Dict[str, float]]:
    """
    Generate realistic synthetic baseline for role.
    Uses AnomalyConfig for session count and random seed.
    """
    rng = np.random.default_rng(AnomalyConfig.RANDOM_SEED)
    n = AnomalyConfig.BASELINE_SESSIONS
    records: List[Dict[str, float]] = []

    for _ in range(n):
        if role == "developer":
            hour     = float(rng.integers(0, 24))
            duration = float(rng.integers(3600, 14400))
            loc_d    = float(round(rng.random() * 5, 2))
        elif role == "executive":
            hour     = float(rng.integers(6, 22))
            duration = float(rng.integers(60, 1800))
            loc_d    = float(round(rng.random() * 500, 2))
        else:
            hour     = float(rng.integers(8, 18))
            duration = float(rng.integers(60, 3600))
            loc_d    = float(round(rng.random() * 15, 2))

        # Compute geographic velocity from location delta + session duration
        geo_vel = float(int((loc_d / max(1.0, duration / 3600.0)) * 100)) / 100.0  # km/h

        rec: Dict[str, float] = {
            "hour":                    hour,
            "day_of_week":             float(rng.integers(0, 7)),
            "login_velocity":          float(rng.integers(1, 4)),
            "failed_ratio":            float(round(rng.random() * 0.1, 4)),
            "location_delta_km":       loc_d,
            "device_match_int":        float(int(rng.integers(0, 2) if role == "developer" else 1)),
            "session_duration_sec":    duration,
            "privilege_escalation_int": 0.0,
            "consecutive_failed_logins": float(rng.integers(0, 2)),
            "new_user_agent_flag":     0.0,
            "geographic_velocity_score": geo_vel,
        }
        records.append(rec)
    return records


def _load_or_generate_baseline(role: str) -> List[Dict[str, float]]:
    """Load existing baseline JSON or generate a new one."""
    path = os.path.normpath(BASELINE_PATH_TEMPLATE.format(role=role))
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Validate that saved baseline has current feature columns
            if isinstance(data, list) and len(data) >= 100:
                if all(feat in data[0] for feat in FEATURE_NAMES):
                    return data  # type: ignore[return-value]
        except Exception:
            pass
    logger.info("Generating new baseline for role: %s", role)
    data = _generate_baseline(role)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data


def _baseline_to_matrix(records: List[Dict[str, float]]) -> np.ndarray:
    rows = []
    for rec in records:
        row: List[float] = []
        for feat in FEATURE_NAMES:
            v = rec.get(feat)
            row.append(float(v if v is not None else DEFAULTS[feat]))
        rows.append(row)
    return np.array(rows, dtype=float)


def _compute_baseline_means(records: List[Dict[str, float]]) -> Dict[str, float]:
    """Compute per-feature means from baseline (used for NaN imputation)."""
    means: Dict[str, float] = {}
    for feat in FEATURE_NAMES:
        vals = [float(r[feat] if r.get(feat) is not None else DEFAULTS[feat]) for r in records]
        means[feat] = float(np.mean(vals)) if len(vals) > 0 else float(DEFAULTS[feat])
    return means


# ─── Model loading ────────────────────────────────────────────────────────────

async def load_anomaly_model(app: Any) -> None:
    """Load or retrain IsolationForest models per role. Stores in app.state."""
    try:
        import joblib  # type: ignore[import]
        from sklearn.ensemble import IsolationForest  # type: ignore[import]

        loop = asyncio.get_event_loop()

        def _load_or_train() -> Dict[str, Any]:
            models:       Dict[str, Any]           = {}
            baseline_means: Dict[str, Dict[str, float]] = {}

            for role in _ROLES:
                joblib_path = os.path.normpath(JOBLIB_PATH_TEMPLATE.format(role=role))

                # Use cached model if available to speed up startup
                if os.path.exists(joblib_path):
                    try:
                        clf = joblib.load(joblib_path)
                        baseline = _load_or_generate_baseline(role)
                        means = _compute_baseline_means(baseline)
                        models[role] = clf
                        baseline_means[role] = means
                        continue
                    except Exception as e:
                        logger.warning("Failed to load cached anomaly model for %s: %s. Retraining.", role, e)
                        pass

                baseline = _load_or_generate_baseline(role)
                means    = _compute_baseline_means(baseline)
                X        = _baseline_to_matrix(baseline)

                clf = IsolationForest(
                    n_estimators=AnomalyConfig.N_ESTIMATORS,
                    contamination=AnomalyConfig.CONTAMINATION, # type: ignore
                    max_samples="auto",
                    random_state=AnomalyConfig.RANDOM_SEED,
                    n_jobs=-1,
                )
                clf.fit(X)

                os.makedirs(os.path.dirname(joblib_path), exist_ok=True)
                joblib.dump(clf, joblib_path)
                models[role]          = clf
                baseline_means[role]  = means

            logger.info("Anomaly IsolationForest retrained for %d roles.", len(_ROLES))
            return {"models": models, "means": baseline_means}

        result = await loop.run_in_executor(None, _load_or_train)  # type: ignore[arg-type]
        app.state.anomaly_models       = result["models"]
        app.state.anomaly_baseline_means = result["means"]
        app.state.anomaly_mode         = "isolation_forest_multiplexed"
        logger.info("Anomaly engine ready.")
    except Exception as exc:
        app.state.anomaly_models = {}
        app.state.anomaly_mode   = "error_fallback"
        logger.error("Anomaly model failed to load: %s", exc)


# ─── SHAP explanation ─────────────────────────────────────────────────────────

def _compute_shap(model: Any, X: np.ndarray) -> List[Dict[str, Any]]:
    """SHAP TreeExplainer — returns top-5 features. Non-fatal on any error."""
    try:
        import shap  # type: ignore[import]
        explainer  = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
        vals = shap_values[0]

        # Guard: all-zero SHAP (model 100% certain)
        if all(v == 0 for v in vals):
            return []

        out_features: List[Dict[str, Any]] = []
        for i, name in enumerate(FEATURE_NAMES):
            w = float(vals[i]) if hasattr(vals, "__getitem__") else 0.0  # type: ignore[index]
            out_features.append({
                "feature":   name.replace("_", " "),
                "weight":    float(int(abs(w) * 1000000)) / 1000000.0,
                "direction": "positive" if w > 0 else "negative",
            })
        return sorted(out_features, key=lambda x: float(str(x["weight"])), reverse=True)[:5]  # type: ignore[index]
    except Exception as exc:
        logger.warning("SHAP anomaly explainer failed (non-fatal): %s", exc)
        return []


# ─── Public entry point ───────────────────────────────────────────────────────

async def detect_anomaly(session_data: Dict[str, Any], app_state: Any) -> Dict[str, Any]:
    """
    Async behavioural anomaly detector using IsolationForest + sigmoid calibration.
    Returns: { confidence, verdict, shap_features, anomaly_score, mode }
    Never raises.
    """
    try:
        models: Dict[str, Any] = getattr(app_state, "anomaly_models", {})
        mode:   str            = getattr(app_state, "anomaly_mode", "error_fallback")
        all_means: Dict[str, Dict[str, float]] = getattr(app_state, "anomaly_baseline_means", {})

        role = str(session_data.get("user_role", "standard")).lower()
        if role not in _ROLES:
            role = "standard"

        model = models.get(role)
        means = all_means.get(role, {})

        # Build and validate feature vector
        try:
            vec = _validate_and_build_vector(session_data, means)
        except ValueError as ve:
            logger.warning("Feature vector error: %s", ve)
            vec = [DEFAULTS[f] for f in FEATURE_NAMES]

        X = np.array([vec], dtype=float)

        if model is None:
            # Heuristic fallback
            fr  = min(1.0, float(session_data.get("failed_ratio", 0.0)))
            pe  = min(1.0, float(session_data.get("privilege_escalation_int", 0.0)))
            lv  = float(session_data.get("login_velocity", 1.0))
            cfl = min(1.0, float(session_data.get("consecutive_failed_logins", 0.0)) / 5.0)
            vel = min(1.0, max(0.0, (lv - 5.0) / 10.0))
            score = float(int(min(1.0, fr * 0.4 + pe * 0.3 + vel * 0.15 + cfl * 0.15) * 10000)) / 10000.0
            verdict = (
                "MALICIOUS"   if score >= AnomalyConfig.MALICIOUS_THRESHOLD
                else "SUSPICIOUS" if score >= AnomalyConfig.SUSPICIOUS_THRESHOLD
                else "BENIGN"
            )
            return {
                "confidence":    score,
                "verdict":       verdict,
                "shap_features": [],
                "anomaly_score": score,
                "mode":          "heuristic_fallback",
            }

        loop = asyncio.get_event_loop()

        def _score() -> Dict[str, Any]:
            # decision_function: positive = inlier, negative = outlier
            df = float(model.decision_function(X)[0]) if hasattr(model, "decision_function") else 0.0  # type: ignore[attr-defined]
            conf = float(int(_sigmoid(df) * 10000)) / 10000.0
            verd = (
                "MALICIOUS"   if conf >= AnomalyConfig.MALICIOUS_THRESHOLD
                else "SUSPICIOUS" if conf >= AnomalyConfig.SUSPICIOUS_THRESHOLD
                else "BENIGN"
            )
            return {"df": df, "conf": conf, "verdict": verd}

        scored = await loop.run_in_executor(None, _score)  # type: ignore[arg-type]
        anomaly_score: float = scored["conf"]
        verdict: str         = scored["verdict"]
        shap_features        = _compute_shap(model, X)

        return {
            "confidence":    anomaly_score,
            "verdict":       verdict,
            "shap_features": shap_features,
            "anomaly_score": anomaly_score,
            "mode":          mode,
        }
    except Exception as exc:
        logger.error("detect_anomaly unhandled error: %s", exc)
        return {
            "confidence":    0.0,
            "verdict":       "BENIGN",
            "shap_features": [],
            "anomaly_score": 0.0,
            "mode":          "error_fallback",
        }
