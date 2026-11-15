"""V3 segment-explanation analysis: SHAP-vs-LIME agreement, tests, case table and figures.

Usage: python analyze_v3.py [--times times_retime.csv]
Protocol: documentation/v3_protocol.md including Amendment 1. Reads only saved results under
results/v3/xai/main; never re-runs the explainers. H1-H3 are decided on the delete rule; the
placeholder rule is the pre-declared secondary analysis.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from src.data import CLASSES, SEED
from src.explain_v3 import chance_jaccard, pair_agreement

ROOT = Path(__file__).resolve().parent
XAI = ROOT / "results" / "v3" / "xai"
MAIN = XAI / "main"
FIG = MAIN / "figures"

K = 3
DISAGREEMENT_THRESHOLD = 0.50
R2_REPORT_LINE = 0.30
N_BOOT = 10_000


def load_values(method):
    long = pd.read_csv(MAIN / f"{method}_values.csv").sort_values(["row_id", "rule", "unit"])
    return {key: g["value"].to_numpy() for key, g in long.groupby(["row_id", "rule"])}


def summarize(values, rng=None):
    v = pd.Series(values, dtype=float).dropna()
    out = {"n": int(len(v)), "mean": round(float(v.mean()), 4), "median": round(float(v.median()), 4),
           "std": round(float(v.std()), 4)}
    if rng is not None and len(v):
        boots = rng.choice(v.to_numpy(), size=(N_BOOT, len(v)), replace=True).mean(axis=1)
        out["mean_ci95"] = [round(float(x), 4) for x in np.percentile(boots, [2.5, 97.5])]
    return out


def wilcoxon(a, b):
    """Paired two-sided Wilcoxon signed-rank; zero differences are dropped (scipy default)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    nonzero = int((a != b).sum())
    if nonzero == 0:
        return {"statistic": None, "p": None, "n_nonzero": 0}
    w = stats.wilcoxon(a, b)
    return {"statistic": float(w.statistic), "p": float(w.pvalue), "n_nonzero": nonzero}


def agreement_block(df, jcol, rcol, rng):
    minus = df[jcol] - df["chance_jaccard"]
    return {
        "jaccard_top3": summarize(df[jcol], rng),
        "chance_jaccard_mean": round(float(df["chance_jaccard"].mean()), 4),
        "jaccard_minus_chance": summarize(minus, rng),
        "wilcoxon_jaccard_vs_chance": wilcoxon(df[jcol], df["chance_jaccard"]),
        "jaccard_value_counts": {str(k): int(v) for k, v in
                                 df[jcol].round(4).value_counts().sort_index().items()},
        "spearman_abs": summarize(df[rcol], rng),
        "spearman_undefined_n": int(df[rcol].isna().sum()),
    }


def class_means(df, cols):
    return {c: {name: round(float(g[col].mean()), 4) for name, col in cols.items()}
            for c, g in df.groupby("pred")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--times", default=None,
                        help="timing file under results/v3/xai/main for RQ3 (default: the main run's own times)")
    args = parser.parse_args(argv)
    FIG.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    sample = pd.read_csv(XAI / "main_sample.csv").set_index("row_id")
    run = pd.read_csv(MAIN / "per_url.csv").set_index("row_id")
    units = pd.read_csv(MAIN / "units.csv", dtype={"text": str}, keep_default_na=False)
    units = units.sort_values(["row_id", "unit"])
    texts = {rid: g["text"].tolist() for rid, g in units.groupby("row_id")}
    shap, lime = load_values("shap"), load_values("lime")
    assert set(run.index) == set(sample.index) == set(texts)

    rows = []
    for rid in run.index:
        sd, ld = shap[(rid, "delete")], lime[(rid, "delete")]
        sp, lp = shap[(rid, "placeholder")], lime[(rid, "placeholder")]
        n = len(sd)
        assert n == run.loc[rid, "n_units"] == len(texts[rid]) == len(ld) == len(sp) == len(lp)
        primary, secondary = pair_agreement(sd, ld, K), pair_agreement(sp, lp, K)
        mask_shap, mask_lime = pair_agreement(sd, sp, K), pair_agreement(ld, lp, K)
        chance = chance_jaccard(n, K)
        rows.append({
            "row_id": rid, "pred": run.loc[rid, "pred"], "true": run.loc[rid, "true"],
            "correct": bool(run.loc[rid, "correct"]), "n_units": n, "chance_jaccard": chance,
            "jaccard_top3": primary["jaccard"], "jaccard_minus_chance": primary["jaccard"] - chance,
            "spearman_abs": primary["spearman"], "n_shared_top3": primary["n_shared"],
            "sign_agreement": primary["sign_agreement"],
            "placeholder_jaccard_top3": secondary["jaccard"],
            "placeholder_jaccard_minus_chance": secondary["jaccard"] - chance,
            "placeholder_spearman_abs": secondary["spearman"],
            "shap_masking_jaccard_top3": mask_shap["jaccard"],
            "shap_masking_spearman_abs": mask_shap["spearman"],
            "lime_masking_jaccard_top3": mask_lime["jaccard"],
            "lime_masking_spearman_abs": mask_lime["spearman"],
            "top3_shap": " | ".join(texts[rid][j] for j in primary["top_a"]),
            "top3_lime": " | ".join(texts[rid][j] for j in primary["top_b"]),
            "url_norm": sample.loc[rid, "url_norm"],
        })
    per_url = pd.DataFrame(rows)
    per_url.to_csv(MAIN / "per_url_agreement.csv", index=False)

    # RQ1: overall agreement under the delete rule (class-balanced by design).
    rq1 = agreement_block(per_url, "jaccard_top3", "spearman_abs", rng)
    shared = per_url["sign_agreement"].notna()
    rq1.update({
        "share_jaccard_below_threshold": round(float((per_url["jaccard_top3"] < DISAGREEMENT_THRESHOLD).mean()), 4),
        "threshold": DISAGREEMENT_THRESHOLD,
        "considerable_disagreement": bool(per_url["jaccard_top3"].mean() < DISAGREEMENT_THRESHOLD),
        "sign_agreement_on_shared_top3": {
            "mean": round(float(per_url.loc[shared, "sign_agreement"].mean()), 4),
            "n_urls_with_shared_unit": int(shared.sum()), "n_urls_without_shared_unit": int((~shared).sum())},
    })

    # RQ2: by predicted class, tested on Jaccard minus chance.
    by_class = {c: {"n": int(len(g)), "mean_n_units": round(float(g["n_units"].mean()), 2),
                    "jaccard_top3_mean": round(float(g["jaccard_top3"].mean()), 4),
                    "chance_jaccard_mean": round(float(g["chance_jaccard"].mean()), 4),
                    "jaccard_minus_chance": summarize(g["jaccard_minus_chance"]),
                    "spearman_abs_mean": round(float(g["spearman_abs"].mean()), 4),
                    "share_jaccard_below_threshold":
                        round(float((g["jaccard_top3"] < DISAGREEMENT_THRESHOLD).mean()), 4)}
                for c, g in per_url.groupby("pred")}
    kw = stats.kruskal(*[g["jaccard_minus_chance"].to_numpy() for _, g in per_url.groupby("pred")])
    rq2 = {"by_predicted_class": by_class,
           "kruskal_wallis_jaccard_minus_chance": {"H": round(float(kw.statistic), 4), "p": float(kw.pvalue)},
           "by_correct_prediction": {str(k): {"n": int(len(g)),
                                              "jaccard_top3_mean": round(float(g["jaccard_top3"].mean()), 4),
                                              "jaccard_minus_chance_mean":
                                                  round(float(g["jaccard_minus_chance"].mean()), 4)}
                                     for k, g in per_url.groupby("correct")}}

    # RQ3: model calls (primary) and wall time (secondary), delete rule only.
    if args.times:
        times = pd.read_csv(MAIN / args.times).set_index("row_id").loc[run.index]
        timing_meta = json.loads((MAIN / "retime_metadata.json").read_text())
    else:
        times = run
        timing_meta = json.loads((MAIN / "explain_metadata.json").read_text())
    q = lambda s, scale=1.0: [round(float(x) * scale, 2) for x in s.quantile([0.25, 0.5, 0.75])]
    ratio = times["shap_s"] / times["lime_s"]
    rq3 = {
        "model_calls": {
            "shap_calls_q25_median_q75": q(run["shap_calls"]),
            "shap_calls_mean": round(float(run["shap_calls"].mean()), 1),
            "lime_calls": sorted(int(x) for x in run["lime_calls"].unique()),
            "share_urls_shap_fewer_calls": round(float((run["shap_calls"] < run["lime_calls"]).mean()), 4),
            "urls_by_n_units": {int(k): int(v) for k, v in run["n_units"].value_counts().sort_index().items()},
            "note": "set by design: exact SHAP needs 2^n calls, LIME always uses its sample budget"},
        "wall_time": {
            "timing_file": args.times or "per_url.csv",
            "timing_conditions_met": bool(timing_meta["power"]["timing_conditions_met"]),
            "shap_ms_q25_median_q75": q(times["shap_s"], 1000),
            "lime_ms_q25_median_q75": q(times["lime_s"], 1000),
            "wilcoxon": wilcoxon(times["shap_s"], times["lime_s"]),
            "median_ratio_shap_over_lime": round(float(ratio.median()), 3),
            "ratio_iqr": [round(float(x), 3) for x in ratio.quantile([0.25, 0.75])],
            "faster_method_by_median": "shap" if times["shap_s"].median() < times["lime_s"].median() else "lime",
            "median_ms_per_1000_calls": {
                "shap": round(float((times["shap_s"] / run["shap_calls"]).median() * 1e6), 1),
                "lime": round(float((times["lime_s"] / run["lime_calls"]).median() * 1e6), 1)}},
    }

    # LIME fit (reported, not gated) and baseline descriptives (Amendment A1.2).
    r2 = float(run["lime_r2"].median())
    lime_fit = {"delete": {"local_r2": summarize(run["lime_r2"]),
                           "median_by_class": run.groupby("pred")["lime_r2"].median().round(4).to_dict(),
                           "median_below_0.30": bool(r2 < R2_REPORT_LINE)},
                "placeholder": {"local_r2": summarize(run["lime_r2_placeholder"]),
                                "median_by_class":
                                    run.groupby("pred")["lime_r2_placeholder"].median().round(4).to_dict()}}
    baseline = {c: {"mean_v_full": round(float(g["v_full"].mean()), 4),
                    "mean_v_empty_delete": round(float(g["v_empty"].mean()), 4),
                    "share_empty_above_full_delete": round(float((g["v_empty"] > g["v_full"]).mean()), 4),
                    "mean_v_empty_placeholder": round(float(g["v_empty_placeholder"].mean()), 4),
                    "share_empty_above_full_placeholder":
                        round(float((g["v_empty_placeholder"] > g["v_full"]).mean()), 4)}
                for c, g in run.groupby("pred")}

    # Secondary: placeholder rule, and sensitivity of each explainer to the masking rule (A1.1).
    secondary = agreement_block(per_url, "placeholder_jaccard_top3", "placeholder_spearman_abs", rng)
    secondary["by_predicted_class"] = class_means(per_url, {
        "jaccard_top3_mean": "placeholder_jaccard_top3",
        "jaccard_minus_chance_mean": "placeholder_jaccard_minus_chance",
        "spearman_abs_mean": "placeholder_spearman_abs"})
    masking = {}
    for method in ("shap", "lime"):
        jcol, rcol = f"{method}_masking_jaccard_top3", f"{method}_masking_spearman_abs"
        masking[method] = {
            "jaccard_top3": summarize(per_url[jcol], rng),
            "jaccard_minus_chance": summarize(per_url[jcol] - per_url["chance_jaccard"], rng),
            "spearman_abs": summarize(per_url[rcol], rng),
            "by_predicted_class": class_means(per_url, {"jaccard_top3_mean": jcol, "spearman_abs_mean": rcol})}
    a, b = per_url["jaccard_top3"], per_url["shap_masking_jaccard_top3"]
    masking["predeclared_comparison"] = {
        "a": "J(SHAP delete, LIME delete): changing the explainer",
        "b": "J(SHAP delete, SHAP placeholder): changing the masking rule",
        "mean_a": round(float(a.mean()), 4), "mean_b": round(float(b.mean()), 4),
        "mean_a_minus_b": round(float((a - b).mean()), 4),
        "urls_a_greater": int((a > b).sum()), "urls_b_greater": int((b > a).sum()),
        "urls_equal": int((a == b).sum()), "wilcoxon": wilcoxon(a, b)}

    # Case table: highest, lowest and one typical example per class (delete rule).
    ordered = per_url.sort_values(["jaccard_top3", "spearman_abs", "row_id"], ascending=[False, False, True])
    cases = [ordered.head(3).assign(case="highest agreement"),
             ordered.tail(3).assign(case="lowest agreement")]
    for c, g in per_url.groupby("pred"):
        g = g.assign(dist=(g["jaccard_top3"] - g["jaccard_top3"].median()).abs())
        cases.append(g.sort_values(["dist", "row_id"]).head(1).drop(columns="dist").assign(case=f"typical {c}"))
    cases = pd.concat(cases)[["case", "row_id", "url_norm", "true", "pred", "correct", "n_units",
                              "jaccard_top3", "spearman_abs", "top3_shap", "top3_lime"]]
    cases.to_csv(MAIN / "case_table.csv", index=False)

    explain_meta = json.loads((MAIN / "explain_metadata.json").read_text())
    summary = {
        "protocol": "documentation/v3_protocol.md incl. Amendment 1",
        "protocol_sha256_at_main_run": explain_meta["protocol_sha256"],
        "k": K, "n_urls": int(len(per_url)), "primary_masking_rule": "delete",
        "rq1_overall": rq1, "rq2_by_class": rq2, "rq3_cost": rq3,
        "lime_fit": lime_fit, "baseline_by_predicted_class": baseline,
        "secondary_placeholder_rule": secondary, "masking_sensitivity": masking,
        "diagnostics": {
            "mean_share_masked_strings_host_without_alnum": round(float(run["share_host_no_alnum"].mean()), 4),
            "max_additivity_err": float(run["additivity_err"].max()),
            "max_proba_err_vs_saved_prediction": float(run["proba_max_abs_err"].max())},
        "caveats": [
            "agreement is consistency, not explanation correctness",
            "explanation units are URL segments; these numbers are not comparable with the V2 study's 0.173",
            "only URLs with at least 6 segments are eligible; results describe longer URLs",
            "sample is balanced by predicted class, so overall means are class-balanced",
            "masked URLs are strings the model never saw"],
    }
    tag = "_retimed" if args.times else ""      # the first summary and cost figure are kept
    with open(MAIN / f"xai_summary{tag}.json", "w") as f:
        json.dump(summary, f, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))

    # Figures
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    levels = [0.0, 0.2, 0.5, 1.0]
    counts = [int(np.isclose(per_url["jaccard_top3"], lv).sum()) for lv in levels]
    axes[0].bar([str(lv) for lv in levels], counts, color="#4c72b0", edgecolor="white")
    axes[0].set(xlabel="Top-3 Jaccard (SHAP vs LIME, delete rule)", ylabel="URLs",
                title=f"Agreement, all {len(per_url)} URLs")
    axes[1].boxplot([per_url.loc[per_url["pred"] == c, "jaccard_minus_chance"] for c in CLASSES],
                    tick_labels=CLASSES)
    axes[1].axhline(0, color="red", ls="--", label="chance")
    axes[1].set(ylabel="Top-3 Jaccard minus chance", title="By predicted class")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(FIG / "agreement.png", dpi=150)
    plt.close(fig)

    bars = [("SHAP vs LIME\n(delete)", rq1["jaccard_top3"]),
            ("SHAP vs LIME\n(placeholder)", secondary["jaccard_top3"]),
            ("SHAP: delete vs\nplaceholder", masking["shap"]["jaccard_top3"]),
            ("LIME: delete vs\nplaceholder", masking["lime"]["jaccard_top3"])]
    fig, ax = plt.subplots(figsize=(7, 4))
    means = [s["mean"] for _, s in bars]
    err = [[m - s["mean_ci95"][0] for m, (_, s) in zip(means, bars)],
           [s["mean_ci95"][1] - m for m, (_, s) in zip(means, bars)]]
    ax.bar([name for name, _ in bars], means, yerr=err, capsize=4,
           color=["#4c72b0", "#4c72b0", "#dd8452", "#dd8452"])
    ax.axhline(per_url["chance_jaccard"].mean(), color="red", ls="--", label="mean chance")
    ax.set(ylabel="Mean top-3 Jaccard (95% CI)", ylim=(0, 1), title="Explainer choice vs masking rule")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "masking_sensitivity.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    by_n = run.groupby("n_units")["shap_calls"].first()
    axes[0].plot(by_n.index, by_n.to_numpy(), "o-", label="exact SHAP (2^n)")
    axes[0].axhline(float(run["lime_calls"].iloc[0]), color="#dd8452", label="LIME budget")
    axes[0].set(xlabel="Units in the URL", ylabel="Model calls per explanation", title="Model calls")
    axes[0].legend()
    axes[1].boxplot([times["shap_s"] * 1000, times["lime_s"] * 1000], tick_labels=["exact SHAP", "LIME (1000)"])
    axes[1].set(ylabel="ms per URL", title="Wall time per explanation")
    fig.tight_layout()
    fig.savefig(FIG / f"cost{tag}.png", dpi=150)
    plt.close(fig)

    print(json.dumps({
        "rq1": {k: rq1[k] for k in ("jaccard_top3", "chance_jaccard_mean", "jaccard_minus_chance",
                                    "wilcoxon_jaccard_vs_chance", "jaccard_value_counts", "spearman_abs",
                                    "share_jaccard_below_threshold", "considerable_disagreement",
                                    "sign_agreement_on_shared_top3")},
        "rq2": {"by_class": {c: {k: v[k] for k in ("mean_n_units", "jaccard_top3_mean", "chance_jaccard_mean")}
                             | {"minus_chance_mean": v["jaccard_minus_chance"]["mean"]}
                             for c, v in by_class.items()},
                "kruskal_wallis_jaccard_minus_chance": rq2["kruskal_wallis_jaccard_minus_chance"],
                "by_correct": rq2["by_correct_prediction"]},
        "rq3": rq3, "lime_fit": lime_fit, "baseline": baseline,
        "secondary_placeholder": {k: secondary[k] for k in ("jaccard_top3", "jaccard_minus_chance", "spearman_abs")},
        "masking_sensitivity": {"shap": {k: masking["shap"][k] for k in ("jaccard_top3", "spearman_abs")},
                                "lime": {k: masking["lime"][k] for k in ("jaccard_top3", "spearman_abs")},
                                "predeclared_comparison": masking["predeclared_comparison"]},
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
