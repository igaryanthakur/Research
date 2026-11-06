"""XAI stage 2: SHAP-LIME agreement, statistical tests, case tables and figures.

Usage: python analyze_v2.py [--times FILE]
Reads only saved results under results/v2/xai; never re-runs the explainers.
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

ROOT = Path(__file__).resolve().parent
XAI = ROOT / "results" / "v2" / "xai"
FIG = XAI / "figures"

K = 5
DISAGREEMENT_THRESHOLD = 0.50
N_BOOT = 10_000


def abs_matrix(method):
    long = pd.read_csv(XAI / f"{method}_explanations.csv")
    wide = long.pivot(index="row_id", columns="feature", values="abs_value")
    return wide.sort_index(axis=1)


def top_k(row):
    """Top-K features by |contribution|; exact ties broken by feature name."""
    order = sorted(row.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _ in order[:K]]


def summarize(values, rng=None):
    v = pd.Series(values).dropna()
    out = {"n": int(len(v)), "mean": round(float(v.mean()), 4), "median": round(float(v.median()), 4),
           "std": round(float(v.std()), 4)}
    if rng is not None and len(v):
        boots = rng.choice(v.to_numpy(), size=(N_BOOT, len(v)), replace=True).mean(axis=1)
        out["mean_ci95"] = [round(float(x), 4) for x in np.percentile(boots, [2.5, 97.5])]
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--times", default="explanation_times.csv",
                        help="timing file under results/v2/xai used for RQ3")
    args = parser.parse_args(argv)
    FIG.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    sample = pd.read_csv(XAI / "xai_sample.csv").set_index("row_id")
    shap_abs, lime_abs = abs_matrix("shap"), abs_matrix("lime")
    assert list(shap_abs.columns) == list(lime_abs.columns)
    assert set(shap_abs.index) == set(lime_abs.index) == set(sample.index)
    lime_abs = lime_abs.loc[shap_abs.index]

    rows = []
    for rid in shap_abs.index:
        s, l = shap_abs.loc[rid], lime_abs.loc[rid]
        ts, tl = top_k(s), top_k(l)
        jac = len(set(ts) & set(tl)) / len(set(ts) | set(tl))
        rho = np.nan if s.nunique() <= 1 or l.nunique() <= 1 else stats.spearmanr(s, l).statistic
        rows.append({"row_id": rid, "pred": sample.loc[rid, "pred"], "true": sample.loc[rid, "true"],
                     "correct": bool(sample.loc[rid, "correct"]), "jaccard_top5": round(jac, 4),
                     "spearman_abs": rho, "top5_shap": ";".join(ts), "top5_lime": ";".join(tl),
                     "url_norm": sample.loc[rid, "url_norm"]})
    per_url = pd.DataFrame(rows)
    per_url.to_csv(XAI / "per_url_agreement.csv", index=False)

    # RQ1: overall agreement (class-balanced by design: 125 URLs per predicted class).
    rq1 = {"jaccard_top5": summarize(per_url["jaccard_top5"], rng),
           "spearman_abs": summarize(per_url["spearman_abs"], rng),
           "spearman_undefined_n": int(per_url["spearman_abs"].isna().sum()),
           "share_jaccard_below_threshold": round(float((per_url["jaccard_top5"] < DISAGREEMENT_THRESHOLD).mean()), 4),
           "jaccard_value_counts": per_url["jaccard_top5"].value_counts().sort_index().to_dict(),
           "threshold": DISAGREEMENT_THRESHOLD}
    rq1["considerable_disagreement"] = rq1["jaccard_top5"]["mean"] < DISAGREEMENT_THRESHOLD

    # RQ2: agreement by predicted class.
    by_class = {c: {"jaccard_top5": summarize(g["jaccard_top5"]), "spearman_abs": summarize(g["spearman_abs"]),
                    "share_jaccard_below_threshold": round(float((g["jaccard_top5"] < DISAGREEMENT_THRESHOLD).mean()), 4)}
                for c, g in per_url.groupby("pred")}
    groups = [g["jaccard_top5"].to_numpy() for _, g in per_url.groupby("pred")]
    kw = stats.kruskal(*groups)
    kw_rho = stats.kruskal(*[g["spearman_abs"].dropna().to_numpy() for _, g in per_url.groupby("pred")])
    by_correct = {str(k): summarize(g["jaccard_top5"]) for k, g in per_url.groupby("correct")}
    rq2 = {"by_predicted_class": by_class,
           "kruskal_wallis_jaccard": {"H": round(float(kw.statistic), 4), "p": float(kw.pvalue)},
           "kruskal_wallis_spearman": {"H": round(float(kw_rho.statistic), 4), "p": float(kw_rho.pvalue)},
           "jaccard_by_correct_prediction": by_correct}

    # RQ3: paired per-URL timing.
    times = pd.read_csv(XAI / args.times).set_index("row_id").loc[shap_abs.index]
    w = stats.wilcoxon(times["shap_s"], times["lime_s"])
    ratio = times["shap_s"] / times["lime_s"]
    q = lambda s: [round(float(x) * 1000, 2) for x in s.quantile([0.25, 0.5, 0.75])]
    rq3 = {"timing_file": args.times, "shap_ms_q25_median_q75": q(times["shap_s"]),
           "lime_ms_q25_median_q75": q(times["lime_s"]),
           "wilcoxon": {"statistic": float(w.statistic), "p": float(w.pvalue)},
           "median_ratio_shap_over_lime": round(float(ratio.median()), 3),
           "ratio_iqr": [round(float(x), 3) for x in ratio.quantile([0.25, 0.75])],
           "faster_method_by_median": "shap" if times["shap_s"].median() < times["lime_s"].median() else "lime",
           "setup": ("exact path-dependent TreeSHAP (all 4 classes per call, 636 rounds x 4 trees, depth 10) "
                     "vs LIME tabular, 2000 perturbations, predicted label only")}

    # Global importance: per-URL normalized |contribution|, averaged.
    glob = pd.DataFrame({
        "shap": shap_abs.div(shap_abs.sum(axis=1).replace(0, np.nan), axis=0).mean(),
        "lime": lime_abs.div(lime_abs.sum(axis=1).replace(0, np.nan), axis=0).mean()})
    glob["shap_rank"] = glob["shap"].rank(ascending=False, method="min").astype(int)
    glob["lime_rank"] = glob["lime"].rank(ascending=False, method="min").astype(int)
    glob = glob.sort_values("shap", ascending=False).round(4)
    glob.to_csv(XAI / "global_importance.csv")
    global_rho = stats.spearmanr(glob["shap"], glob["lime"]).statistic

    lime_fit = pd.read_csv(XAI / "lime_fit.csv")
    lime_summary = {"local_r2": summarize(lime_fit["local_r2"]),
                    "local_r2_by_class": {c: summarize(g["local_r2"]) for c, g in lime_fit.groupby("pred")}}

    # Sensitivity: LIME self-agreement across seeds and its SHAP agreement at more perturbations.
    stability = None
    if (XAI / "lime_stability.csv").exists():
        st = pd.read_csv(XAI / "lime_stability.csv")
        tops = {key: top_k(g.set_index("feature")["abs_value"])
                for key, g in st.groupby(["row_id", "num_samples", "seed"])}
        jac = lambda a, b: len(set(a) & set(b)) / len(set(a) | set(b))
        recs = []
        for rid in st["row_id"].unique():
            shap_top = top_k(shap_abs.loc[rid])
            for n in sorted(st["num_samples"].unique()):
                s1, s2 = sorted(st["seed"].unique())
                recs.append({"row_id": rid, "num_samples": n,
                             "lime_self_jaccard": jac(tops[(rid, n, s1)], tops[(rid, n, s2)]),
                             "shap_lime_jaccard": jac(shap_top, tops[(rid, n, s1)])})
        recs = pd.DataFrame(recs)
        recs.to_csv(XAI / "lime_stability_summary.csv", index=False)
        stability = {str(n): {"n_urls": int(len(g)),
                              "lime_self_jaccard_mean": round(float(g["lime_self_jaccard"].mean()), 4),
                              "shap_lime_jaccard_mean": round(float(g["shap_lime_jaccard"].mean()), 4)}
                     for n, g in recs.groupby("num_samples")}

    # Case table: highest, lowest and one median-agreement example per class.
    ordered = per_url.sort_values(["jaccard_top5", "spearman_abs", "row_id"], ascending=[False, False, True])
    cases = [ordered.head(3).assign(case="highest agreement"),
             ordered.tail(3).assign(case="lowest agreement")]
    for c, g in per_url.groupby("pred"):
        g = g.assign(dist=(g["jaccard_top5"] - g["jaccard_top5"].median()).abs())
        cases.append(g.sort_values(["dist", "row_id"]).head(1).drop(columns="dist").assign(case=f"typical {c}"))
    cases = pd.concat(cases)[["case", "row_id", "url_norm", "true", "pred", "correct", "jaccard_top5",
                              "spearman_abs", "top5_shap", "top5_lime"]]
    cases.to_csv(XAI / "case_table.csv", index=False)

    summary = {"k": K, "n_urls": int(len(per_url)), "rq1_overall": rq1, "rq2_by_class": rq2,
               "rq3_timing": rq3, "global_importance_spearman": round(float(global_rho), 4),
               "global_top10": {"shap": glob.sort_values("shap_rank").index[:10].tolist(),
                                "lime": glob.sort_values("lime_rank").index[:10].tolist()},
               "lime_fit": lime_summary, "lime_stability_sensitivity": stability,
               "caveats": ["agreement is not explanation correctness",
                           "SHAP values are in log-odds space, LIME weights in probability space; "
                           "comparison is rank-based",
                           "sample is balanced by predicted class, so overall means are class-balanced"]}
    with open(XAI / "xai_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))

    # Figures
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(per_url["jaccard_top5"], bins=np.linspace(0, 1, 12), color="#4c72b0", edgecolor="white")
    axes[0].axvline(DISAGREEMENT_THRESHOLD, color="red", ls="--", label="0.50 threshold")
    axes[0].set(xlabel="Top-5 Jaccard (SHAP vs LIME)", ylabel="URLs", title="Agreement, all 500 URLs")
    axes[0].legend()
    axes[1].boxplot([per_url.loc[per_url["pred"] == c, "jaccard_top5"] for c in CLASSES], tick_labels=CLASSES)
    axes[1].axhline(DISAGREEMENT_THRESHOLD, color="red", ls="--")
    axes[1].set(ylabel="Top-5 Jaccard", title="By predicted class")
    fig.tight_layout()
    fig.savefig(FIG / "jaccard_distribution.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.boxplot([times["shap_s"] * 1000, times["lime_s"] * 1000], tick_labels=["TreeSHAP", "LIME (2000)"])
    ax.set_yscale("log")
    ax.set(ylabel="ms per URL (log scale)", title="Per-instance explanation time")
    fig.tight_layout()
    fig.savefig(FIG / "timing_boxplot.png", dpi=150)
    plt.close(fig)

    top = glob.sort_values("shap", ascending=False).head(12)[::-1]
    fig, ax = plt.subplots(figsize=(7, 5))
    y = np.arange(len(top))
    ax.barh(y - 0.2, top["shap"], 0.4, label="SHAP")
    ax.barh(y + 0.2, top["lime"], 0.4, label="LIME")
    ax.set_yticks(y, top.index)
    ax.set(xlabel="Mean normalized |contribution|", title="Global importance (top 12 by SHAP)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "global_importance.png", dpi=150)
    plt.close(fig)

    print(json.dumps({"rq1": {k: rq1[k] for k in ("jaccard_top5", "spearman_abs", "share_jaccard_below_threshold",
                                                   "considerable_disagreement", "spearman_undefined_n")},
                      "rq2": {"jaccard_mean_by_class": {c: v["jaccard_top5"]["mean"] for c, v in by_class.items()},
                              "kruskal_wallis_jaccard": rq2["kruskal_wallis_jaccard"],
                              "by_correct": by_correct},
                      "rq3": rq3, "global_rho": round(float(global_rho), 4),
                      "global_top10": summary["global_top10"], "lime_r2": lime_summary["local_r2"],
                      "lime_stability": stability},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
