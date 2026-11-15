"""Freeze the V3 release: write results/v3/freeze.json with checksums and the environment.

Usage: python freeze_v3.py
Refuses to run if results/v3/freeze.json already exists.
"""
import json
import platform
import subprocess
from importlib.metadata import version as pkg_version
from pathlib import Path

from src.freeze import ROOT, freeze_path, write_freeze

PACKAGES = ["numpy", "pandas", "scikit-learn", "xgboost", "lightgbm", "catboost", "shap",
            "lime", "scipy", "rapidfuzz", "joblib", "pyarrow"]
SOURCES = ["src/features.py", "src/features_v2.py", "src/features_v3.py", "src/data.py",
           "prepare_v3.py", "train_v3.py"]
RELEASE_URL = "https://github.com/igaryanthakur/Research/releases/download/v3/v3.zip"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def release_files():
    art = sorted(p for p in (ROOT / "artifacts" / "v3").rglob("*") if p.is_file())
    res = sorted(p for p in (ROOT / "results" / "v3").rglob("*")
                 if p.is_file() and p.name != "freeze.json"
                 and "xai" not in p.relative_to(ROOT / "results" / "v3").parts)
    return [p.relative_to(ROOT).as_posix() for p in art + res] + SOURCES


def main():
    if freeze_path("v3").exists():
        raise SystemExit("results/v3/freeze.json exists: V3 is already frozen.")
    files = release_files()
    status = git("status", "--porcelain")
    manifest = write_freeze(
        "v3", files,
        model="stack_lr_xgb_lgbm (XGBoost + LightGBM -> LogisticRegression), 348 features",
        policy=("Freeze protects against accidental change. The V3 test set was reported for V1/V2 "
                "before V3 was designed; V3 results are not pre-registered."),
        notes={
            "stack_bases": ("The base models used at test time live inside artifacts/v3/final_model.joblib; "
                            "stack_base_train_*.joblib are the validation-stage (train-only) models."),
            "excluded": "results/v3/freeze.json itself and everything under results/v3/xai/",
        },
        release={"tag": "v3", "url": RELEASE_URL,
                 "contents": "zip of the artifacts/v3 folder",
                 "zip_sha256": None,
                 "zip_sha256_note": ("not recorded: the zip was not downloaded; the per-file hashes of "
                                     "artifacts/v3 below are what explain_v3.py checks")},
        environment={"python": platform.python_version(), "platform": platform.platform(),
                     "processor": platform.processor(),
                     **{p: pkg_version(p) for p in PACKAGES}},
        git={"head": git("rev-parse", "HEAD"), "dirty": bool(status),
             "dirty_files": status.splitlines()},
    )
    print(f"Froze {len(manifest['sha256'])} files; git {manifest['git']['head'][:7]} "
          f"dirty={manifest['git']['dirty']}")
    print(json.dumps(manifest["environment"], indent=2))


if __name__ == "__main__":
    main()
