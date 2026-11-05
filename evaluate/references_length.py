"""Step 3: References, publication years, and output length versus performance.

Uses judge run 1, avoiding duplicate counting of identical model outputs
that were scored twice. Missing GPT52 text metadata stays missing until added.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/analysis/research"


def correlation(x, y):
    """Return both correlations; undefined for small or constant samples."""
    values = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(values) < 3 or values["x"].nunique() < 2 or values["y"].nunique() < 2:
        return {"n": len(values), "pearson_r": np.nan, "pearson_p": np.nan,
                "spearman_r": np.nan, "spearman_p": np.nan}
    r, p = pearsonr(values["x"], values["y"])
    rho, sp = spearmanr(values["x"], values["y"])
    return {"n": len(values), "pearson_r": r, "pearson_p": p,
            "spearman_r": rho, "spearman_p": sp}


def main():
    scores = pd.read_csv(OUT / "case_scores.csv", dtype={"case_id": str})
    scores = scores[scores["judge_run"] == 1].copy()  # considering only one gpt4.1 outcome
    scores["score"] = pd.to_numeric(scores["score"], errors="coerce")
    text_path = OUT / "text_metrics.csv"
    text_df = pd.read_csv(text_path, dtype={"case_id": str}) if text_path.stat().st_size else pd.DataFrame()
    if text_df.empty:
        print("No text metrics available yet; retaining rows with missing metrics.")
        text_df = pd.DataFrame(columns=["user", "model", "case_id", "word_count",
                                        "reference_count", "average_reference_year"])
    else:
        text_df = text_df[text_df["judge_run"] == 1].copy()
        # Flag repeated summaries rather than allowing accidental many-to-many merges.
        duplicates = text_df.duplicated(["user", "model", "case_id"], keep=False)
        if duplicates.any():
            raise ValueError("Duplicate text summaries for same user, model, case. Inspect text_metrics.csv")
    data = scores.merge(text_df.drop(columns=["judge_run"], errors="ignore"),
                        on=["user", "model", "case_id"], how="left", validate="one_to_one")
    for col in ["word_count", "reference_count", "average_reference_year"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data.to_csv(OUT / "length_reference_case_data.csv", index=False)

    # Descriptive results; 0 citations is different from missing citation data.
    descriptions = []
    for (user, model), sub in data.groupby(["user", "model"]):
        counts = sub["reference_count"]
        descriptions.append({
            "user": user, "model": model, "n_scores": sub["score"].notna().sum(),
            "n_length_available": sub["word_count"].notna().sum(),
            "n_reference_data_available": counts.notna().sum(),
            "n_zero_references": (counts == 0).sum(),
            "mean_words": sub["word_count"].mean(),
            "sd_words": sub["word_count"].std(),
            "mean_references": counts.mean(),
            "sd_references": counts.std(),
            "mean_reference_year": sub["average_reference_year"].mean(),
            "sd_reference_year": sub["average_reference_year"].std(),
            "n_reference_headings": (sub["has_references_heading"] == True).sum() if "has_references_heading" in sub else 0,
            "n_source_domain_flags": (sub["source_domain_flag"] == True).sum() if "source_domain_flag" in sub else 0,
        })
    pd.DataFrame(descriptions).to_csv(OUT / "reference_length_summary.csv", index=False)

    rows = []
    # Two datasets: all responses and only responses with ≥1 reference.
    for subset_name, subset in [("all_responses", data),
                                ("with_references", data[data["reference_count"] >= 1])]:
        groups = [("all_models_both_users", "All", subset)]
        groups += [(f"user_{user}", "All", grp) for user, grp in subset.groupby("user")]
        groups += [(f"model_{model}", "All", grp) for model, grp in subset.groupby("model")]
        groups += [(f"user_{user}", model, grp)
                   for (user, model), grp in subset.groupby(["user", "model"])]
        for group, model, grp in groups:
            for feature in ["word_count", "reference_count", "average_reference_year"]:
                rows.append({"subset": subset_name, "group": group, "model": model,
                             "predictor": feature, "n_responses": len(grp),
                             "n_missing_predictor": grp[feature].isna().sum(),
                             **correlation(grp[feature], grp["score"])})
    pd.DataFrame(rows).to_csv(OUT / "performance_correlations.csv", index=False)
    print(f"Saved text metrics, correlation inputs, and correlations in {OUT}")
    print("Note: pooled p-values treat responses as independent; LB/SJ share cases.")


if __name__ == "__main__":
    main()
