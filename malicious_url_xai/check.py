"""Score one URL with the trained four-class model."""
import argparse
import sys
from pathlib import Path

import joblib

from src.features import build_feature_frame, normalize_url

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify one URL with the trained model.")
    parser.add_argument("url", help="URL to check")
    args = parser.parse_args(argv)

    model_path = ART / "final_model.joblib"
    encoder_path = ART / "label_encoder.joblib"
    if not model_path.exists() or not encoder_path.exists():
        sys.exit("Missing model artifacts. Run python train.py first.")

    normalized = normalize_url(args.url)
    frame = build_feature_frame([normalized])
    model = joblib.load(model_path)
    encoder = joblib.load(encoder_path)
    probabilities = model.predict_proba(frame)[0]
    index = int(probabilities.argmax())

    print(f"Normalized URL: {normalized}")
    print(f"Prediction: {encoder.classes_[index]}")
    print("Class scores:")
    ranked = sorted(zip(encoder.classes_, probabilities), key=lambda item: item[1], reverse=True)
    for label, probability in ranked:
        print(f"  {label}: {probability:.2%}")


if __name__ == "__main__":
    main()
