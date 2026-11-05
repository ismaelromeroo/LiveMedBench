"""Step 2: Judge repeatability, LB-vs-SJ agreement, and clinical-axis errors."""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/analysis/research"


def compare_pairs(data, keys, left_name, right_name, value):
    """Compare paired values after matching on IDs, never on row positions."""
    left = data.loc[data["group"] == left_name, keys + [value]].rename(columns={value: "left"})
    right = data.loc[data["group"] == right_name, keys + [value]].rename(columns={value: "right"})
    paired = left.merge(right, on=keys, how="inner", validate="one_to_one")
    paired = paired.dropna(subset=["left", "right"])
    if paired.empty:
        return {"n_pairs": 0, "mean_difference": np.nan, "mean_absolute_difference": np.nan,
                "exact_agreement": np.nan, "pearson_r": np.nan, "wilcoxon_p": np.nan}
    d = paired["left"] - paired["right"]
    if (d == 0).all():
        p = 1.0
    elif len(d) < 2:
        p = np.nan
    else:
        p = stats.wilcoxon(d).pvalue
    r = (stats.pearsonr(paired["left"], paired["right"]).statistic
         if len(paired) >= 3 and paired["left"].nunique() > 1 and paired["right"].nunique() > 1
         else np.nan)
    result = {"n_pairs": len(paired), "mean_difference": d.mean(),
              "mean_absolute_difference": d.abs().mean(),
              "exact_agreement": (d == 0).mean(), "pearson_r": r, "wilcoxon_p": p}
    if value == "met":
        # Binary rubric labels: met=1, not met=0. Report both classes equally.
        tp = ((paired["left"] == 1) & (paired["right"] == 1)).sum()
        tn = ((paired["left"] == 0) & (paired["right"] == 0)).sum()
        fp = ((paired["left"] == 1) & (paired["right"] == 0)).sum()
        fn = ((paired["left"] == 0) & (paired["right"] == 1)).sum()
        f1_met = 2 * tp / (2 * tp + fp + fn) if (tp + fp) and (tp + fn) else np.nan
        f1_not = 2 * tn / (2 * tn + fp + fn) if (tn + fp) and (tn + fn) else np.nan
        actual_pos = (tp + fn) / len(paired)
        pred_pos = (tp + fp) / len(paired)
        chance = actual_pos * pred_pos + (1 - actual_pos) * (1 - pred_pos)
        result.update({"f1_met": f1_met, "f1_not_met": f1_not,
                       "macro_f1": (f1_met + f1_not) / 2,
                       "cohen_kappa": ((tp + tn) / len(paired) - chance) / (1 - chance)
                       if chance < 1 else np.nan})
    return result


def comparisons(df, value, keys):
    rows = []
    # Same model output, user, and cases; different GPT judge runs (1 vs 2).
    for (user, model), sub in df.groupby(["user", "model"]):
        sub = sub.copy()
        sub["group"] = sub["judge_run"].astype(str)
        res = compare_pairs(sub, keys, "1", "2", value)
        rows.append({"comparison": "GPT judge run 1 vs 2", "user": user,
                     "model": model, **res})
    # Two users running the same model; compare like-for-like judge runs.
    for (judge_run, model), sub in df.groupby(["judge_run", "model"]):
        sub = sub.copy()
        sub["group"] = sub["user"]
        res = compare_pairs(sub, keys, "LB", "SJ", value)
        rows.append({"comparison": "LB vs SJ", "judge_run": judge_run,
                     "model": model, **res})
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(OUT / "case_scores.csv", dtype={"case_id": str})
    if df.empty:
        raise ValueError("No scores found. Run 01_prepare.py after generating metric_all.json files.")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["judge_run"] = df["judge_run"].astype(int)

    # Preserve original, possibly negative normalized scores from metric_all.json.
    summary = (df.groupby(["user", "judge_run", "model"], as_index=False)
               .agg(n_cases=("score", "count"), mean_score=("score", "mean"),
                    sd_score=("score", "std")))
    # 95% t interval around the mean, as in the original notebook.
    se = summary["sd_score"] / np.sqrt(summary["n_cases"])
    margin = stats.t.ppf(0.975, summary["n_cases"] - 1) * se
    summary["ci95_low"] = summary["mean_score"] - margin
    summary["ci95_high"] = summary["mean_score"] + margin
    summary.to_csv(OUT / "score_summary.csv", index=False)
    comparisons(df, "score", ["model", "case_id"]).to_csv(
        OUT / "case_score_stability.csv", index=False)

    # Models were tested on the same cases. Friedman is a paired alternative
    # to the notebook's Kruskal-Wallis test (which assumes independent groups).
    model_tests = []
    for (user, judge_run), sub in df.groupby(["user", "judge_run"]):
        wide = sub.pivot(index="case_id", columns="model", values="score").dropna()
        if wide.shape[1] >= 3 and len(wide) >= 3:
            test = stats.friedmanchisquare(*(wide[c] for c in wide.columns))
            statistic, p_value = test.statistic, test.pvalue
        else:
            statistic, p_value = np.nan, np.nan
        model_tests.append({"user": user, "judge_run": judge_run,
                            "models": ", ".join(wide.columns), "n_common_cases": len(wide),
                            "friedman_statistic": statistic, "p_value": p_value})
    pd.DataFrame(model_tests).to_csv(OUT / "model_comparison_friedman.csv", index=False)

    # Compare individual rubric decisions as well (more informative than scores alone).
    rubric_file = OUT / "rubric_judgments.csv"
    if rubric_file.exists() and rubric_file.stat().st_size > 0:
        rubrics = pd.read_csv(rubric_file, dtype={"case_id": str})
        if not rubrics.empty:
            keys = ["model", "case_id", "rubric_item"]
            comparisons(rubrics, "met", keys).to_csv(
                OUT / "rubric_met_stability.csv", index=False)

            # Exact agreement at each medical axis, by model and user.
            rows = []
            for axis, sub in rubrics.groupby("axis"):
                result = comparisons(sub, "met", keys)
                result.insert(0, "axis", axis)
                rows.append(result)
            pd.concat(rows, ignore_index=True).to_csv(
                OUT / "rubric_stability_by_axis.csv", index=False)

    axis_file = OUT / "axis_errors.csv"
    if axis_file.exists():
        axes = pd.read_csv(axis_file, dtype={"case_id": str})
        if not axes.empty:
            axes.groupby(["user", "judge_run", "model", "axis"], as_index=False).agg(
                n_cases=("case_id", "nunique"), n_criteria=("n_criteria", "sum"),
                mean_case_error_rate=("error_rate", "mean"),
                mean_case_accuracy=("accuracy", "mean")
            ).to_csv(OUT / "axis_summary.csv", index=False)
            # Each axis is compared on exactly the same case IDs.
            rows = []
            for axis, sub in axes.groupby("axis"):
                result = comparisons(sub, "error_rate", ["model", "case_id", "axis"])
                result.insert(0, "axis", axis)
                rows.append(result)
            pd.concat(rows, ignore_index=True).to_csv(
                OUT / "axis_error_stability.csv", index=False)
    print(f"Saved stability and axis results in {OUT}")


if __name__ == "__main__":
    main()
