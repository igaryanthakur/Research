"""Score one URL with the trained four-class model (V2 artifacts, falling back to V1)."""
import argparse
import json
import sys
from pathlib import Path

import joblib

from src.features import build_feature_frame, normalize_url
from src.features_v2 import build_feature_frame_v2

ROOT = Path(__file__).resolve().parent
ART_V2 = ROOT / "artifacts" / "v2"
ART_V1 = ROOT / "artifacts"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify one URL with the trained model.")
    parser.add_argument("url", help="URL to check")
    args = parser.parse_args(argv)

    art = ART_V2 if (ART_V2 / "final_model.joblib").exists() else ART_V1
    model_path = art / "final_model.joblib"
    encoder_path = art / "label_encoder.joblib"
    if not model_path.exists() or not encoder_path.exists():
        sys.exit("Missing model artifacts. Run python prepare_v2.py and python train_v2.py first.")

    normalized = normalize_url(args.url)
    if art == ART_V2:
        columns = json.loads((art / "feature_names.json").read_text())
        frame = build_feature_frame_v2([normalized])[columns]
    else:
        frame = build_feature_frame([normalized])
    model = joblib.load(model_path)
    encoder = joblib.load(encoder_path)
    probabilities = model.predict_proba(frame)[0]
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
