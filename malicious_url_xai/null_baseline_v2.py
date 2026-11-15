"""Post-hoc null baselines for the saved V2 SHAP-LIME agreement results.

Usage: python null_baseline_v2.py
Reads only saved CSVs under results/v2/xai; never re-runs the explainers and never touches
xai_summary.json. Writes null_baseline.json and null_baseline_by_class.csv.
"""
import json
from datetime import datetime
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from src.data import CLASSES, SEED

ROOT = Path(__file__).resolve().parent
XAI = ROOT / "results" / "v2" / "xai"

K = 5
N_PERM = 10_000


def chance_jaccard(n, k):
    """Exact expected Jaccard of two independent uniformly random k-subsets of n items."""
    total = comb(n, k)
    return sum(comb(k, h) * comb(n - k, k - h) / total * h / (2 * k - h) for h in range(k + 1))


def abs_matrix(method):
    long = pd.read_csv(XAI / f"{method}_explanations.csv")
    wide = long.pivot(index="row_id", columns="feature", values="abs_value")
    return wide.sort_index(axis=1)


def indicator(tops, features):
    pos = {f: j for j, f in enumerate(features)}
    out = np.zeros((len(tops), len(features)), dtype=np.int64)
    for i, names in enumerate(tops):
        for name in names:
            out[i, pos[name]] = 1
    return out


def spearman_matrix(a, b):
    """Spearman of every row of a against every row of b (average ranks, as scipy)."""
    ra = stats.rankdata(a, axis=1)
    rb = stats.rankdata(b, axis=1)
    ra = ra - ra.mean(axis=1, keepdims=True)
    rb = rb - rb.mean(axis=1, keepdims=True)
    na = np.sqrt((ra ** 2).sum(axis=1))
    nb = np.sqrt((rb ** 2).sum(axis=1))
    with np.errstate(divide="ignore", invalid="ignore"):
        return (ra @ rb.T) / np.outer(na, nb)


def null_stats(matrix, rng):
    """Observed (diagonal) vs exhaustive off-diagonal null and a within-group permutation test."""
    n = matrix.shape[0]
    diag = np.diag(matrix)
    off = matrix[~np.eye(n, dtype=bool)]
    off = off[np.isfinite(off)]
    observed = float(np.nanmean(diag))
    perm_means = np.array([np.nanmean(matrix[np.arange(n), rng.permutation(n)])
                           for _ in range(N_PERM)])
    centre = perm_means.mean()
    extreme = np.abs(perm_means - centre) >= abs(observed - centre)
    return {
        "observed_mean": round(observed, 4),
        "null_mean": round(float(off.mean()), 4),
        "null_pair_p2_5_p97_5": [round(float(x), 4) for x in np.percentile(off, [2.5, 97.5])],
        "null_n_pairs": int(off.size),
        "observed_minus_null": round(observed - float(off.mean()), 4),
        "perm_mean_p2_5_p97_5": [round(float(x), 4) for x in np.percentile(perm_means, [2.5, 97.5])],
        "perm_p_two_sided": round(float((extreme.sum() + 1) / (N_PERM + 1)), 5),
    }, perm_means, observed


def main():
    rng = np.random.default_rng(SEED)
    per_url = pd.read_csv(XAI / "per_url_agreement.csv").sort_values("row_id").reset_index(drop=True)
    shap_abs = abs_matrix("shap").loc[per_url["row_id"]]
    lime_abs = abs_matrix("lime").loc[per_url["row_id"]]
    features = list(shap_abs.columns)
    assert features == list(lime_abs.columns) and len(features) == 36

    s_ind = indicator(per_url["top5_shap"].str.split(";"), features)
    l_ind = indicator(per_url["top5_lime"].str.split(";"), features)
    assert (s_ind.sum(axis=1) == K).all() and (l_ind.sum(axis=1) == K).all()

    uniform = chance_jaccard(len(features), K)
    by_class, rows = {}, []
    perm_j, perm_r, obs_j, obs_r = [], [], [], []
    for c in CLASSES:
        idx = np.flatnonzero(per_url["pred"].to_numpy() == c)
        inter = s_ind[idx] @ l_ind[idx].T
        jac = inter / (2 * K - inter)
        assert np.allclose(np.diag(jac), per_url.loc[idx, "jaccard_top5"], atol=1e-4)
        rho = spearman_matrix(shap_abs.iloc[idx].to_numpy(), lime_abs.iloc[idx].to_numpy())
        saved = per_url.loc[idx, "spearman_abs"].to_numpy()
        ok = np.isfinite(saved)
        assert np.allclose(np.diag(rho)[ok], saved[ok], atol=1e-6)

        j_stats, j_perm, j_obs = null_stats(jac, rng)
        r_stats, r_perm, r_obs = null_stats(rho, rng)
        perm_j.append(j_perm); perm_r.append(r_perm); obs_j.append(j_obs); obs_r.append(r_obs)
        by_class[c] = {"n_urls": int(len(idx)), "uniform_chance_jaccard": round(uniform, 4),
                       "jaccard_top5": j_stats, "spearman_abs": r_stats}
        rows.append({"pred": c, "n_urls": len(idx), "uniform_chance_jaccard": round(uniform, 4),
                     **{f"jaccard_{k}": v for k, v in j_stats.items()},
                     **{f"spearman_{k}": v for k, v in r_stats.items()}})

    def overall(perms, obs):
        # Classes have equal size (125 each), so the overall mean is the mean of class means.
        perm_means = np.mean(perms, axis=0)
        observed = float(np.mean(obs))
        centre = perm_means.mean()
        extreme = np.abs(perm_means - centre) >= abs(observed - centre)
        return {"observed_mean": round(observed, 4),
                "null_mean_same_class": round(float(centre), 4),
                "perm_mean_p2_5_p97_5": [round(float(x), 4) for x in np.percentile(perm_means, [2.5, 97.5])],
                "perm_p_two_sided": round(float((extreme.sum() + 1) / (N_PERM + 1)), 5)}

    run_date = datetime.now().date().isoformat()
    summary = {
        "analysis": f"post-hoc, added {run_date} after results were seen",
        "source_files": ["per_url_agreement.csv", "shap_explanations.csv", "lime_explanations.csv"],
        "k": K, "n_features": len(features), "n_urls": int(len(per_url)),
        "uniform_chance_jaccard_exact": round(uniform, 4),
        "uniform_chance_definition": "expected Jaccard of two independent uniformly random 5-subsets of 36 features",
        "same_class_null_definition": ("SHAP explanation of URL i paired with the LIME explanation of every other "
                                       "URL j != i with the same predicted class; exhaustive over all pairs"),
        "permutation_test": (f"{N_PERM} within-class random permutations of the LIME assignment (seed {SEED}); "
                             "two-sided p-value of the observed mean against the permutation distribution"),
        "overall": {"jaccard_top5": overall(perm_j, obs_j), "spearman_abs": overall(perm_r, obs_r)},
        "by_predicted_class": by_class,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(XAI / "null_baseline.json", "w") as f:
        json.dump(summary, f, indent=2)
    pd.DataFrame(rows).to_csv(XAI / "null_baseline_by_class.csv", index=False)

    print(f"Uniform chance (exact) top-{K} of {len(features)}: {uniform:.4f}")
    print(json.dumps(summary["overall"], indent=2))
    for c, v in by_class.items():
        j, r = v["jaccard_top5"], v["spearman_abs"]
        print(f"{c:11s} J obs {j['observed_mean']:.4f} null {j['null_mean']:.4f} p {j['perm_p_two_sided']:.5f} | "
              f"rho obs {r['observed_mean']:.4f} null {r['null_mean']:.4f} p {r['perm_p_two_sided']:.5f}")


if __name__ == "__main__":
    main()
