"""Score one URL with the latest trained four-class model (V3 -> V2 -> V1)."""
import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

from src.features import build_feature_frame, normalize_url
from src.features_v2 import build_feature_frame_v2
from src.features_v3 import build_feature_frame_v3_lexical

ROOT = Path(__file__).resolve().parent
ART_V3 = ROOT / "artifacts" / "v3"
ART_V2 = ROOT / "artifacts" / "v2"
ART_V1 = ROOT / "artifacts"


def _pick_artifacts():
    for art in (ART_V3, ART_V2, ART_V1):
        if (art / "final_model.joblib").exists() and (art / "label_encoder.joblib").exists():
            return art
    return None


def _v3_frame(normalized: str, columns):
    lexical = build_feature_frame_v3_lexical([normalized])
    vectorizer = joblib.load(ART_V3 / "ngram_vectorizer.joblib")
    ngram = vectorizer.transform([normalized]).toarray()
    ngram_names = [f"ng_{g}" for g in vectorizer.get_feature_names_out()]
    import pandas as pd
    full = pd.concat(
        [lexical.astype(np.float32),
         pd.DataFrame(ngram, columns=ngram_names, dtype=np.float32)],
        axis=1,
    )
    return full[columns]


def _predict_proba(bundle, frame):
    if isinstance(bundle, dict) and "meta" in bundle and "bases" in bundle:
        blocks = [np.asarray(bundle["bases"][f].predict_proba(frame)) for f in bundle["families"]]
        return bundle["meta"].predict_proba(np.hstack(blocks))[0]
    if isinstance(bundle, dict) and "bases" in bundle and bundle.get("method") == "mean_proba":
        blocks = [np.asarray(bundle["bases"][f].predict_proba(frame)) for f in ("xgb", "lgbm", "cat")]
        return np.mean(blocks, axis=0)[0]
    if isinstance(bundle, dict) and "model" in bundle:
        return np.asarray(bundle["model"].predict_proba(frame))[0]
    return np.asarray(bundle.predict_proba(frame))[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify one URL with the trained model.")
    parser.add_argument("url", help="URL to check")
    args = parser.parse_args(argv)

    art = _pick_artifacts()
    if art is None:
        sys.exit("Missing model artifacts. Run prepare_v3.py / train_v3.py (or V2) first.")

    normalized = normalize_url(args.url)
    columns = json.loads((art / "feature_names.json").read_text()) if (art / "feature_names.json").exists() else None
    if art == ART_V3:
        frame = _v3_frame(normalized, columns)
    elif art == ART_V2:
        frame = build_feature_frame_v2([normalized])[columns]
    else:
        frame = build_feature_frame([normalized])

    bundle = joblib.load(art / "final_model.joblib")
    encoder = joblib.load(art / "label_encoder.joblib")
    probabilities = _predict_proba(bundle, frame)
    index = int(probabilities.argmax())

    print(f"Model: {art.relative_to(ROOT)}")
    print(f"Normalized URL: {normalized}")
    print(f"Prediction: {encoder.classes_[index]}")
    print("Class scores:")
    ranked = sorted(zip(encoder.classes_, probabilities), key=lambda item: item[1], reverse=True)
    for label, probability in ranked:
        print(f"  {label}: {probability:.2%}")


if __name__ == "__main__":
    main()
