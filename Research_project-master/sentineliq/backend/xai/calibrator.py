"""
xai/calibrator.py — Platt scaling for post-hoc confidence calibration.

Raw model logits systematically over-confident or under-confident.
Platt scaling maps raw scores to true probabilities using a tiny
logistic regression trained on the same test cases used by test_accuracy.py.

Usage:
    cal = PlattCalibrator("phishing")
    cal.fit(raw_scores, true_labels)       # once, from benchmark run
    p = cal.calibrate(0.87)                # returns true probability
"""

import os
import logging
import numpy as np # type: ignore[import]
from typing import List, Optional

logger = logging.getLogger("sentineliq.calibrator")

_CALIBRATOR_DIR = os.path.join(os.path.dirname(__file__), "..", "db")


class PlattCalibrator:
    """
    Wraps any engine's raw confidence score and maps it to a true
    probability using Platt scaling (logistic regression on raw scores).

    Graceful fallback: returns raw_score unchanged when not fitted.
    """

    def __init__(self, engine_name: str) -> None:
        self.engine_name = str(engine_name)
        self._model: Optional[Any] = None  # type: ignore[name-defined]
        self._fitted = False
        self._path = os.path.join(
            _CALIBRATOR_DIR, f"calibrator_{self.engine_name}.joblib"
        )
        self._try_load()

    def _try_load(self) -> None:
        """Silently load a previously saved calibrator if it exists."""
        if not os.path.exists(self._path):
            return
        try:
            import joblib  # type: ignore[import]
            self._model = joblib.load(self._path)
            self._fitted = True
            logger.info("Calibrator loaded for %s.", self.engine_name)
        except Exception as exc:
            logger.warning("Calibrator load failed for %s: %s", self.engine_name, exc)

    def fit(self, raw_scores: List[float], true_labels: List[int]) -> None:
        """
        Train the calibrator on a list of raw scores and binary labels.
        Call once after running test_accuracy.py.  Saves to db/.
        """
        try:
            from sklearn.linear_model import LogisticRegression  # type: ignore[import]
            import joblib  # type: ignore[import]

            X = np.array(raw_scores, dtype=float).reshape(-1, 1)
            y = np.array(true_labels, dtype=int)

            if len(np.unique(y)) < 2:
                logger.warning("Calibrator for %s: only one class in labels — skipping fit.", self.engine_name)
                return

            model = LogisticRegression(C=1.0, max_iter=500, random_state=42)
            model.fit(X, y)
            self._model = model
            self._fitted = True
            os.makedirs(_CALIBRATOR_DIR, exist_ok=True)
            joblib.dump(model, self._path)
            logger.info("Calibrator saved for %s.", self.engine_name)
        except Exception as exc:
            logger.error("Calibrator fit failed for %s: %s", self.engine_name, exc)

    def calibrate(self, raw_score: float) -> float:
        """
        Return calibrated probability in [0, 1].
        Falls back to raw_score if not fitted.
        """
        if not self._fitted or self._model is None:
            return float(raw_score)
        try:
            prob = self._model.predict_proba([[float(raw_score)]])[0][1] # type: ignore[attr-defined]
            return float(round(float(prob), 4)) # type: ignore[call-overload]
        except Exception:
            return float(raw_score)


# ── Module-level singletons (loaded once at import time) ───────────────────
_calibrators: dict = {}


def get_calibrator(engine_name: str) -> PlattCalibrator:
    """Return a (possibly cached) calibrator for the given engine."""
    global _calibrators
    if engine_name not in _calibrators:
        _calibrators[engine_name] = PlattCalibrator(engine_name)
    return _calibrators[engine_name]


def calibrate_confidence(engine_name: str, raw_score: float) -> float:
    """One-line helper used by engine detect_* functions."""
    return get_calibrator(engine_name).calibrate(raw_score)


# ── Type annotation fix for Optional[Any] ────────────────────────────────
from typing import Any  # noqa: E402  (imported here to avoid top-level Any noise)
