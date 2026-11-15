"""V3 segment-explanation experiment (protocol: documentation/v3_protocol.md).

Usage: python explain_v3.py --pilot | --main | --retime
--pilot   smoke test on 20 held-out test URLs; applies the protocol's gates.
--main    exact Shapley values and LIME weights for the main sample under the delete rule
          (primary) and the placeholder rule (secondary, Amendment 1). Runs once.
--retime  timing-only pass over the main sample (delete rule); values are checked against the
          saved ones and only the times are written.
None of these computes SHAP-vs-LIME agreement; that is analyze_v3.py. Every mode refuses to run
unless results/v3/freeze.json checks clean, and saved explanations are never regenerated.
"""
import argparse
import hashlib
import json
import subprocess
import time
import warnings
from datetime import datetime
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import stats

from src.data import CLASSES
from src.explain_v3 import (
    MIN_SEGMENTS, StackModel, coalition_values, exact_shapley, jaccard, lime_segments, segments,
    top_k, unit_text, units,
)
from src.features import hostname
from src.freeze import check_frozen
from src.runinfo import environment, peak_memory_mb

warnings.filterwarnings("ignore", message=".*(GPU|grow_gpu_hist|device).*")

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts" / "v3"
RES = ROOT / "results" / "v3"
OUT = RES / "xai"
PILOT = OUT / "pilot"
MAIN = OUT / "main"
PROTOCOL = ROOT.parent / "documentation" / "v3_protocol.md"

PILOT_PER_CLASS = (2, 2, 1)          # low, middle, high segment-count tertile
PILOT_SEED = 7
MAIN_SEED = 42
LIME_SEED_OFFSET = 42
RULES = ("delete", "placeholder")    # primary, secondary (Amendment 1)
TOL_RETIME = 1e-9
BEST_PERFORMANCE_OVERLAY = "ded574b5-45a0-4f42-8737-46345c09c238"
LIME_SAMPLES = 1000
LIME_SAMPLES_LADDER = 4000
STABILITY_SEED_OFFSET = 10_042
TIME_BUDGET_S = 7200
MAX_PER_CLASS, MIN_PER_CLASS = 50, 25
Q1_RANGE, Q1_MIN_URLS, Q1_DELETION = 0.10, 14, 0.05
Q3_SELF_JACCARD = 0.50
Q2_REPORT_LINE = 0.30
TOL_FEATURES, TOL_PROBA, TOL_ADDITIVITY = 1e-6, 1e-5, 1e-6


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def power_state():
    """Power source and Windows power mode, for the protocol's timing conditions.

    battery_status is Win32_Battery (1 = discharging). power_online is the WMI BatteryStatus flag
    for mains power. overlay_ac is the Windows power mode used when plugged in; the GUID
    ded574b5-... is "Best performance". timing_conditions_met is true only on mains power with
    that mode active.
    """
    def ps(cmd):
        try:
            return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                                  text=True, timeout=30).stdout.strip()
        except Exception as exc:
            return f"unavailable ({exc})"
    key = r"'HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes'"
    state = {
        "battery_status": ps("(Get-CimInstance Win32_Battery).BatteryStatus"),
        "power_online": ps("(Get-CimInstance -Namespace root\\wmi -ClassName BatteryStatus).PowerOnline"),
        "power_scheme": ps("powercfg /getactivescheme"),
        "overlay_ac": ps(f"(Get-ItemProperty {key}).ActiveOverlayAcPowerScheme"),
        "overlay_dc": ps(f"(Get-ItemProperty {key}).ActiveOverlayDcPowerScheme"),
    }
    state["timing_conditions_met"] = bool(
        state["power_online"].lower() == "true"
        and state["overlay_ac"].lower() == BEST_PERFORMANCE_OVERLAY)
    return state


def run_metadata(model, **extra):
    return {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "git_head": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
        "lime_samples": LIME_SAMPLES, "total_model_calls": model.calls,
        "peak_memory_mb": peak_memory_mb(), "power": power_state(),
        "environment": {**environment(), "shap": metadata.version("shap"),
                        "lime": metadata.version("lime"), "lightgbm": metadata.version("lightgbm")},
        **extra,
    }


def load_test():
    df = pd.read_parquet(ART / "clean.parquet", columns=["url_norm"])
    preds = pd.read_csv(RES / "test_predictions.csv")
    preds["url_norm"] = df.loc[preds["row_id"], "url_norm"].to_numpy()
    preds["n_segments"] = preds["url_norm"].map(lambda u: len(segments(u)))
    return preds


def draw_pilot(preds):
    path = OUT / "pilot_sample.csv"
    if path.exists():
        return pd.read_csv(path)
    eligible = preds[preds["n_segments"] >= MIN_SEGMENTS]
    picks = []
    for c in CLASSES:
        pool = eligible[eligible["pred"] == c].copy()
        pool["tertile"] = pd.qcut(pool["n_segments"].rank(method="first"), 3, labels=["low", "mid", "high"])
        for tertile, k in zip(["low", "mid", "high"], PILOT_PER_CLASS):
            picks.append(pool[pool["tertile"] == tertile].sample(n=k, random_state=PILOT_SEED))
    sample = pd.concat(picks).sort_values(["pred", "n_segments", "row_id"]).reset_index(drop=True)
    assert len(sample) == 20 and (sample["n_segments"] > 10).sum() >= 2
    cols = ["row_id", "url_norm", "true", "pred", "n_segments", "tertile",
            *[f"proba_{c}" for c in CLASSES]]
    OUT.mkdir(parents=True, exist_ok=True)
    sample[cols].to_csv(path, index=False)
    return sample[cols]


def stored_features(row_ids, columns):
    """Saved feature rows; the parquet index is a 0..N-1 range, so row_id is the row position."""
    table = pq.read_table(ART / "features_v3_full.parquet", columns=columns)
    rows = table.take(pa.array(np.asarray(row_ids, dtype=np.int64)))
    return rows.to_pandas()[columns].to_numpy(dtype=np.float64)


def explain_one(model, url, cls, row_id, lime_samples, placeholder=True):
    u = units(url)
    n = len(u)

    def value_fn(strings):
        return model.predict_proba(strings)[:, cls]

    t0 = time.perf_counter()
    values, strings = coalition_values(value_fn, url, u)
    phi = exact_shapley(values, n)
    shap_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    lime = lime_segments(value_fn, url, u, lime_samples, seed=42 + row_id)
    lime_s = time.perf_counter() - t0
    lime_b = lime_segments(value_fn, url, u, lime_samples, seed=STABILITY_SEED_OFFSET + row_id)

    full = 2 ** n - 1
    single = [abs(values[full] - values[full & ~(1 << i)]) for i in range(n)]
    rec = {
        "n_units": n, "shap_calls": 2 ** n, "lime_calls": lime["calls"],
        "shap_s": shap_s, "lime_s": lime_s, "total_s": shap_s + lime_s,
        "v_full": values[full], "v_empty": values[0],
        "v_range": float(values.max() - values.min()),
        "max_single_deletion": float(max(single)),
        "abs_full_minus_empty": float(abs(values[full] - values[0])),
        "additivity_err": float(abs(phi.sum() - (values[full] - values[0]))),
        "all_finite": bool(np.isfinite(values).all() and np.isfinite(lime["weights"]).all()),
        "lime_r2": lime["r2"], "lime_r2_seed2": lime_b["r2"],
        "lime_self_jaccard_top3": jaccard(top_k(lime["weights"]), top_k(lime_b["weights"])),
        "share_empty_hostname": float(np.mean([hostname(s) == "" for s in strings])),
        "empty_string": strings[0],
    }
    if placeholder:
        ph_values, _ = coalition_values(value_fn, url, u, rule="placeholder")
        ph_phi = exact_shapley(ph_values, n)
        rec["shap_delete_vs_placeholder_spearman"] = float(
            stats.spearmanr(np.abs(phi), np.abs(ph_phi)).statistic)
    examples = [strings[b] for b in sorted({full & ~1, full & ~(1 << (n - 1)), (1 << (n // 2)), 0})]
    return rec, phi, values, lime, examples


def cross_check_shap(values, n):
    """Exact Shapley vs shap.ExactExplainer on the coalition table of one URL."""
    import shap
    lookup = lambda m: values[(np.asarray(m, dtype=int) << np.arange(n)).sum(axis=1)]
    explainer = shap.ExactExplainer(lookup, shap.maskers.Independent(np.zeros((1, n))))
    ref = explainer(np.ones((1, n))).values[0]
    return float(np.max(np.abs(ref - exact_shapley(values, n))))


def pilot():
    check_frozen("v3")
    if (PILOT / "pilot_decision.json").exists():
        raise SystemExit("The pilot has already run; its outputs are never regenerated.")
    PILOT.mkdir(parents=True, exist_ok=True)
    preds = load_test()
    sample = draw_pilot(preds)
    model = StackModel()
    cls_index = {c: i for i, c in enumerate(CLASSES)}

    # G0: unmasked features and probabilities reproduce the saved ones.
    recomputed = model.featurize(sample["url_norm"]).to_numpy(dtype=np.float64)
    stored = stored_features(sample["row_id"], model.columns)
    feat_err = np.abs(recomputed - stored).max(axis=1)
    proba = model.predict_proba(sample["url_norm"])
    proba_err = np.abs(proba - sample[[f"proba_{c}" for c in CLASSES]].to_numpy()).max(axis=1)

    warm = preds[(preds["n_segments"] >= MIN_SEGMENTS) & ~preds["row_id"].isin(sample["row_id"])]
    warm = warm.sort_values("row_id").iloc[0]
    explain_one(model, warm["url_norm"], cls_index[warm["pred"]], int(warm["row_id"]),
                LIME_SAMPLES, placeholder=False)

    recs, shap_rows, lime_rows, example_rows, cross = [], [], [], [], None
    for i, row in enumerate(sample.itertuples(index=False)):
        cls = cls_index[row.pred]
        rec, phi, values, lime, examples = explain_one(model, row.url_norm, cls, int(row.row_id),
                                                       LIME_SAMPLES)
        if cross is None and rec["n_units"] == 6:
            try:
                cross = {"row_id": int(row.row_id), "method": "shap.ExactExplainer",
                         "max_abs_diff": cross_check_shap(values, rec["n_units"])}
            except Exception as exc:  # brute force over all orderings instead
                from itertools import permutations
                n, brute = rec["n_units"], np.zeros(rec["n_units"])
                for order in permutations(range(n)):
                    bits = 0
                    for j in order:
                        brute[j] += values[bits | 1 << j] - values[bits]
                        bits |= 1 << j
                cross = {"row_id": int(row.row_id), "method": f"brute-force n! orderings ({exc})",
                         "max_abs_diff": float(np.max(np.abs(brute / 720 - phi)))}
        recs.append({"row_id": row.row_id, "pred": row.pred, "true": row.true,
                     "n_segments": row.n_segments, "tertile": row.tertile,
                     "feature_max_abs_err": feat_err[i], "proba_max_abs_err": proba_err[i], **rec})
        for j, (p, w) in enumerate(zip(phi, lime["weights"])):
            shap_rows.append({"row_id": row.row_id, "pred": row.pred, "unit": j, "value": p})
            lime_rows.append({"row_id": row.row_id, "pred": row.pred, "unit": j, "value": w})
        for s in examples:
            example_rows.append({"row_id": row.row_id, "url_norm": row.url_norm, "masked": s})
        print(f"{i + 1:2d}/20 {row.pred:10s} n={rec['n_units']:2d} shap {rec['shap_s']:6.2f}s "
              f"lime {rec['lime_s']:6.2f}s r2 {rec['lime_r2']:.3f} range {rec['v_range']:.3f}", flush=True)

    per_url = pd.DataFrame(recs)
    per_url.to_csv(PILOT / "pilot_per_url.csv", index=False)
    pd.DataFrame(shap_rows).to_csv(PILOT / "pilot_shap_values.csv", index=False)
    pd.DataFrame(lime_rows).to_csv(PILOT / "pilot_lime_values.csv", index=False)
    pd.DataFrame(example_rows).to_csv(PILOT / "pilot_masked_examples.csv", index=False)

    decision = decide(per_url, cross)
    meta = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "git_head": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
        "lime_samples": LIME_SAMPLES, "pilot_seed": PILOT_SEED, "warmup_row_id": int(warm["row_id"]),
        "total_model_calls": model.calls, "peak_memory_mb": peak_memory_mb(),
        "power": power_state(),
        "environment": environment(),
    }
    with open(PILOT / "pilot_decision.json", "w") as f:
        json.dump({**decision, "metadata": meta}, f, indent=2, default=float)
    print(json.dumps(decision, indent=2, default=float))


def decide(per_url, cross):
    g0 = {
        "features_match": bool((per_url["feature_max_abs_err"] <= TOL_FEATURES).all()),
        "feature_max_abs_err": float(per_url["feature_max_abs_err"].max()),
        "proba_match": bool((per_url["proba_max_abs_err"] <= TOL_PROBA).all()),
        "proba_max_abs_err": float(per_url["proba_max_abs_err"].max()),
        "additivity": bool((per_url["additivity_err"] <= TOL_ADDITIVITY).all()),
        "additivity_max_err": float(per_url["additivity_err"].max()),
        "all_finite": bool(per_url["all_finite"].all()),
    }
    g0["pass"] = all(v for k, v in g0.items() if isinstance(v, bool))
    q1_urls = int((per_url["v_range"] >= Q1_RANGE).sum())
    q1_del = float(per_url["max_single_deletion"].median())
    q1 = {"urls_range_ge_0.10": q1_urls, "median_max_single_deletion": q1_del,
          "pass": q1_urls >= Q1_MIN_URLS and q1_del >= Q1_DELETION}
    q3_val = float(per_url["lime_self_jaccard_top3"].mean())
    q3 = {"mean_lime_self_jaccard_top3": q3_val, "pass": q3_val >= Q3_SELF_JACCARD}
    t90 = float(per_url["total_s"].quantile(0.9))
    n_class = int(min(MAX_PER_CLASS, TIME_BUDGET_S // (4 * t90)))
    r = {"t90_total_s": t90, "median_shap_s": float(per_url["shap_s"].median()),
         "median_lime_s": float(per_url["lime_s"].median()), "n_class": n_class,
         "projected_full_run_min": round(4 * n_class * t90 / 60, 1), "pass": n_class >= MIN_PER_CLASS}
    r2 = float(per_url["lime_r2"].median())
    q2 = {"median_lime_r2": r2, "by_class": per_url.groupby("pred")["lime_r2"].median().round(4).to_dict(),
          "below_0.30": r2 < Q2_REPORT_LINE, "gated": False}
    go = g0["pass"] and q1["pass"] and q3["pass"] and r["pass"]
    if go:
        next_step = f"GO: main run with n_class = {n_class} per predicted class"
    elif not g0["pass"]:
        next_step = "G0 failed: bug, fix and rerun the pilot"
    elif not q1["pass"]:
        next_step = "Q1 failed: Draft 4 fallback"
    elif not q3["pass"]:
        next_step = f"Q3 failed: ladder step 1, rerun pilot LIME with {LIME_SAMPLES_LADDER} samples"
    else:
        next_step = "R failed: ladder step 2"
    return {"pilot_is_smoke_test": True, "n_urls": int(len(per_url)),
            "n_units_counts": {int(k): int(v) for k, v in
                               per_url["n_units"].value_counts().sort_index().items()},
            "G0": g0, "Q1": q1, "Q3": q3, "R": r, "Q2_reported": q2,
            "masking_diagnostic": {
                "median_shap_delete_vs_placeholder_spearman":
                    float(per_url["shap_delete_vs_placeholder_spearman"].median()),
                "mean_share_empty_hostname": float(per_url["share_empty_hostname"].mean())},
            "shap_cross_check": cross, "go": go, "next_step": next_step}


# ---------------------------------------------------------------- main run (protocol + Amendment 1)

def draw_main(preds, n_class):
    """n_class eligible test URLs per predicted class (seed 42), pilot URLs excluded.

    Saved before any model call and never redrawn.
    """
    path = OUT / "main_sample.csv"
    if not path.exists():
        pilot_ids = pd.read_csv(OUT / "pilot_sample.csv")["row_id"]
        pool = preds[(preds["n_segments"] >= MIN_SEGMENTS) & ~preds["row_id"].isin(pilot_ids)]
        sample = pd.concat([pool[pool["pred"] == c].sample(n=n_class, random_state=MAIN_SEED)
                            for c in CLASSES])
        sample = sample.sort_values(["pred", "row_id"]).reset_index(drop=True)
        sample["correct"] = sample["true"] == sample["pred"]
        cols = ["row_id", "url_norm", "true", "pred", "correct", "n_segments",
                *[f"proba_{c}" for c in CLASSES]]
        sample[cols].to_csv(path, index=False)
    sample = pd.read_csv(path)
    truth = preds.set_index("row_id").loc[sample["row_id"], "url_norm"].to_numpy()
    assert (sample["url_norm"].to_numpy() == truth).all(), "main_sample.csv URLs differ from clean.parquet"
    return sample


def explain_rule(value_fn, url, unit_spans, seed, rule):
    """Exact Shapley values, then LIME, for one URL under one masking rule; each part is timed."""
    n = len(unit_spans)
    t0 = time.perf_counter()
    values, strings = coalition_values(value_fn, url, unit_spans, rule)
    phi = exact_shapley(values, n)
    shap_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    lime = lime_segments(value_fn, url, unit_spans, LIME_SAMPLES, seed=seed, rule=rule)
    lime_s = time.perf_counter() - t0
    return {"values": values, "strings": strings, "phi": phi, "lime": lime,
            "shap_s": shap_s, "lime_s": lime_s}


def host_has_no_alnum(url: str) -> bool:
    return not any(ch.isascii() and ch.isalnum() for ch in hostname(url))


def warm_up(model, preds, cls_index, rules):
    """Explain the first eligible test row (by row_id) that is not in the pilot, untimed."""
    pilot_ids = pd.read_csv(OUT / "pilot_sample.csv")["row_id"]
    pool = preds[(preds["n_segments"] >= MIN_SEGMENTS) & ~preds["row_id"].isin(pilot_ids)]
    warm = pool.sort_values("row_id").iloc[0]
    cls = cls_index[warm["pred"]]
    for rule in rules:
        explain_rule(lambda s: model.predict_proba(s)[:, cls], warm["url_norm"],
                     units(warm["url_norm"]), LIME_SEED_OFFSET + int(warm["row_id"]), rule)
    return int(warm["row_id"])


def main_run():
    check_frozen("v3")
    decision = json.loads((PILOT / "pilot_decision.json").read_text())
    if not decision["go"]:
        raise SystemExit("The pilot decision is not GO; the main run must not start.")
    if (MAIN / "per_url.csv").exists():
        raise SystemExit("The main run has already produced results; explanations are never "
                         "regenerated. Use --retime for a timing-only pass.")
    n_class = int(decision["R"]["n_class"])
    preds = load_test()
    sample = draw_main(preds, n_class)
    assert (sample["pred"].value_counts() == n_class).all() and len(sample) == n_class * len(CLASSES)
    assert not set(pd.read_csv(OUT / "pilot_sample.csv")["row_id"]) & set(sample["row_id"])
    MAIN.mkdir(parents=True, exist_ok=True)

    model = StackModel()
    cls_index = {c: i for i, c in enumerate(CLASSES)}
    proba = model.predict_proba(sample["url_norm"])
    proba_err = np.abs(proba - sample[[f"proba_{c}" for c in CLASSES]].to_numpy()).max(axis=1)
    assert (proba_err <= TOL_PROBA).all(), "stack output differs from test_predictions.csv"
    assert [CLASSES[i] for i in proba.argmax(axis=1)] == sample["pred"].tolist()

    warm_id = warm_up(model, preds, cls_index, RULES)
    recs, value_rows, unit_rows = [], {"shap": [], "lime": []}, []
    t_start = time.perf_counter()
    for i, row in enumerate(sample.itertuples(index=False)):
        url, cls, row_id = row.url_norm, cls_index[row.pred], int(row.row_id)
        u = units(url)
        n = len(u)
        full = 2 ** n - 1

        def value_fn(strings, cls=cls):
            return model.predict_proba(strings)[:, cls]

        # Delete rule first: its two timed parts are the RQ3 measurements (Amendment A1.4).
        res = {rule: explain_rule(value_fn, url, u, LIME_SEED_OFFSET + row_id, rule) for rule in RULES}
        d, p = res["delete"], res["placeholder"]
        add_err = max(abs(r["phi"].sum() - (r["values"][full] - r["values"][0])) for r in res.values())
        finite = all(np.isfinite(r["values"]).all() and np.isfinite(r["lime"]["weights"]).all()
                     for r in res.values())
        assert add_err <= TOL_ADDITIVITY and finite, (row_id, add_err, finite)
        assert abs(d["values"][full] - getattr(row, f"proba_{row.pred}")) <= TOL_PROBA
        assert abs(d["values"][full] - p["values"][full]) <= 1e-12

        single = [abs(d["values"][full] - d["values"][full & ~(1 << j)]) for j in range(n)]
        recs.append({
            "row_id": row_id, "pred": row.pred, "true": row.true, "correct": bool(row.correct),
            "n_segments": int(row.n_segments), "n_units": n,
            "shap_calls": 2 ** n, "lime_calls": d["lime"]["calls"],
            "shap_s": d["shap_s"], "lime_s": d["lime_s"],
            "shap_placeholder_s": p["shap_s"], "lime_placeholder_s": p["lime_s"],
            "v_full": d["values"][full], "v_empty": d["values"][0],
            "v_empty_placeholder": p["values"][0],
            "v_range": float(d["values"].max() - d["values"].min()),
            "v_range_placeholder": float(p["values"].max() - p["values"].min()),
            "max_single_deletion": float(max(single)),
            "lime_r2": d["lime"]["r2"], "lime_r2_placeholder": p["lime"]["r2"],
            "lime_intercept": d["lime"]["intercept"], "lime_local_pred": d["lime"]["local_pred"],
            "proba_max_abs_err": proba_err[i], "additivity_err": float(add_err),
            "share_host_no_alnum": float(np.mean([host_has_no_alnum(s) for s in d["strings"]])),
            "empty_string": d["strings"][0], "empty_string_placeholder": p["strings"][0],
        })
        for rule, r in res.items():
            for j in range(n):
                base = {"row_id": row_id, "pred": row.pred, "rule": rule, "unit": j}
                value_rows["shap"].append({**base, "value": r["phi"][j]})
                value_rows["lime"].append({**base, "value": r["lime"]["weights"][j]})
        for j, unit in enumerate(u):
            unit_rows.append({"row_id": row_id, "unit": j, "n_segments_in_unit": len(unit),
                              "text": unit_text(url, unit)})
        if (i + 1) % 25 == 0:
            print(f"{i + 1:3d}/{len(sample)} {row.pred:10s} n={n:2d} shap {d['shap_s']:.2f}s "
                  f"lime {d['lime_s']:.2f}s", flush=True)
    elapsed = time.perf_counter() - t_start

    per_url = pd.DataFrame(recs)
    per_url.to_csv(MAIN / "per_url.csv", index=False)
    for method, rows in value_rows.items():
        pd.DataFrame(rows).to_csv(MAIN / f"{method}_values.csv", index=False)
    pd.DataFrame(unit_rows).to_csv(MAIN / "units.csv", index=False)
    meta = run_metadata(model, mode="main", n_class=n_class, n_urls=int(len(sample)),
                        main_seed=MAIN_SEED, lime_seed="42 + row_id", rules=list(RULES),
                        warmup_row_id=warm_id, elapsed_s=round(elapsed, 1))
    with open(MAIN / "explain_metadata.json", "w") as f:
        json.dump(meta, f, indent=2, default=float)
    print(f"Main run saved: {len(per_url)} URLs in {elapsed / 60:.1f} min, {model.calls} model calls. "
          f"Timing conditions met: {meta['power']['timing_conditions_met']}.")
    if not meta["power"]["timing_conditions_met"]:
        print("Wall times are provisional. Re-measure with: python explain_v3.py --retime "
              "(on charger, Windows power mode Best performance).")


def retime():
    """Timing-only pass (Amendment A1.4): delete rule, values checked against the saved ones."""
    check_frozen("v3")
    if not (MAIN / "per_url.csv").exists():
        raise SystemExit("Run --main first.")
    preds = load_test()
    sample = pd.read_csv(OUT / "main_sample.csv")
    saved = {}
    for method in ("shap", "lime"):
        long = pd.read_csv(MAIN / f"{method}_values.csv")
        long = long[long["rule"] == "delete"].sort_values(["row_id", "unit"])
        saved[method] = {rid: g["value"].to_numpy() for rid, g in long.groupby("row_id")}

    model = StackModel()
    cls_index = {c: i for i, c in enumerate(CLASSES)}
    warm_id = warm_up(model, preds, cls_index, ("delete",))
    rows = []
    for i, row in enumerate(sample.itertuples(index=False)):
        cls, row_id = cls_index[row.pred], int(row.row_id)
        u = units(row.url_norm)
        r = explain_rule(lambda s, cls=cls: model.predict_proba(s)[:, cls], row.url_norm, u,
                         LIME_SEED_OFFSET + row_id, "delete")
        assert np.allclose(r["phi"], saved["shap"][row_id], atol=TOL_RETIME), row_id
        assert np.allclose(r["lime"]["weights"], saved["lime"][row_id], atol=TOL_RETIME), row_id
        rows.append({"row_id": row_id, "pred": row.pred, "n_units": len(u), "shap_calls": 2 ** len(u),
                     "lime_calls": r["lime"]["calls"], "shap_s": r["shap_s"], "lime_s": r["lime_s"]})
        if (i + 1) % 50 == 0:
            print(f"{i + 1:3d}/{len(sample)}", flush=True)
    pd.DataFrame(rows).to_csv(MAIN / "times_retime.csv", index=False)
    meta = run_metadata(model, mode="retime", n_urls=int(len(sample)), warmup_row_id=warm_id)
    with open(MAIN / "retime_metadata.json", "w") as f:
        json.dump(meta, f, indent=2, default=float)
    print(f"Retime saved. Values reproduce the saved explanations. "
          f"Timing conditions met: {meta['power']['timing_conditions_met']}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", action="store_true", help="run the 20-URL pilot")
    mode.add_argument("--main", action="store_true", help="run the main experiment once")
    mode.add_argument("--retime", action="store_true", help="timing-only pass over the main sample")
    args = parser.parse_args(argv)
    if args.pilot:
        pilot()
    elif args.main:
        main_run()
    else:
        retime()


if __name__ == "__main__":
    main()
