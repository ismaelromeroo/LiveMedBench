"""Combine LiveMedBench GPT/physician rubric scores and calculate HealthBench Macro F1.

Run from anywhere: python evaluate/extract_ai_judge_score.py
Requires: pandas, openpyxl

Physician workbook format:
- Row 1: headings such as "Model_D__Case_1138_Rubric_1 — Accuracy — 8 points"
- Rows 2 onward: one physician per row; rubric scores are 0 or the signed rubric weight
- Model A/B/C/D correspond to the FIRST appearance of each model in cases_40.xlsx
"""

import json
import re
import shutil
from pathlib import Path

import pandas as pd
from scipy.stats import pearsonr



# --------------------------- File locations ---------------------------
ROOT = Path(__file__).resolve().parents[1]  # Repository root when script is in evaluate/
print(ROOT)

FILES = {
    "Doximity Ask Instant": ROOT / "outputs/LB/evaluation_results_input_Doximity_Ask_Instant_2026-09-10.json",
    "Doximity Ask Thinking": ROOT / "outputs/LB/evaluation_results_input_Doximity_Ask_Thinking_2026-09-10.json",
    "OpenEvidence Sackett": ROOT / "outputs/LB/evaluation_results_input_OpenEvidence_Regular_2026-09-10.json",
    "GPT52": ROOT / "outputs/gpt52_1/evaluation_results_gpt52_1.json",
}

CASES_FILE = ROOT / "data/subset-livemedbench/cases_40.xlsx"
PHYSICIANS_FILE = ROOT / "data/subset-livemedbench/AI_Clinical_Tool_Evaluation_Data.xlsx"  # Adjust if needed
RUBRIC_FILE = ROOT / "data/subset-livemedbench/Subset_LiveMedBench_v202604_new.json"  # Adjust if needed
OUTPUT_DIR = ROOT / "outputs/analysis"


# --------------------------- Step 1: Join scores ---------------------------
def prepare_scores():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    selections = pd.read_excel(CASES_FILE)
    if not {"case_id", "model"}.issubset(selections.columns):
        raise ValueError("cases_40.xlsx must have 'case_id' and 'model' columns")

    # Model A, B, C, ... follow first appearance in cases_40.xlsx.
    models = selections["model"].drop_duplicates().tolist()
    model_letters = {model: chr(65 + i) for i, model in enumerate(models)}
    print("Model letters:", model_letters)

    with open(RUBRIC_FILE, encoding="utf-8") as f:
        rubrics = {int(x["case_id"]): x["rubric_items"] for x in json.load(f)}

    # Load all GPT judgments, indexed by model and case.
    results = {}
    for model in models:
        with open(FILES[model], encoding="utf-8") as f:
            results[model] = {int(x["case_id"]): x["evaluations"] for x in json.load(f)}

    # Keep an unchanged copy of the original physician spreadsheet.
    shutil.copy2(PHYSICIANS_FILE, OUTPUT_DIR / "01_physician_responses_original.xlsx")
    physician_data = pd.read_excel(PHYSICIANS_FILE)

    # Find rubric columns; everything else (e.g. respondent identifiers) is ignored.
    pattern = re.compile(r"Model_([A-Z])_+Case_(\d+)_+Rubric_(\d+)", re.I)
    physician_columns = {}
    for col in physician_data.columns:
        match = pattern.search(str(col))
        if match:
            key = (match.group(1).upper(), int(match.group(2)), int(match.group(3)))
            if key in physician_columns:
                raise ValueError(f"Duplicate physician rubric column: {key}")
            physician_columns[key] = col
    if not physician_columns:
        raise ValueError("No rubric columns found in physician spreadsheet. Check headers.")
    # print(physician_columns) e.g., ('D', 1138, 0): 'Model_D__Case_1138_Rubric_0 — Accuracy — 10 points',

    # One physician per nonempty row (beginning with Excel row 2).
    active = physician_data[list(physician_columns.values())].notna().any(axis=1)
    physician_data = physician_data.loc[active].reset_index(drop=True)
    physicians = [f"judge_{i + 1}" for i in range(len(physician_data))]
    if len(physicians) < 2:
        raise ValueError("At least two physician rows are needed for physician agreement")
    print(f"Detected {len(physicians)} physicians: {', '.join(physicians)}")

    rows = []
    for _, selection in selections.iterrows():
        case_id = int(selection["case_id"])
        model = selection["model"]
        if case_id not in rubrics or case_id not in results[model]:
            raise KeyError(f"Missing rubric or GPT evaluation: case {case_id}, {model}")

        for number, rubric in enumerate(rubrics[case_id], start=0): # start=1
            key = (model_letters[model], case_id, number)
            if key not in physician_columns:
                raise KeyError(f"Physician column missing for {key}. Check model order and headers.")
            evaluation = results[model][case_id].get(f"rubric_{number+1}")
            if evaluation is None:
                raise KeyError(f"GPT rubric_{number} missing: case {case_id}, {model}")

            record = {
                "case_id": case_id,
                "model": model,
                "model_letter": model_letters[model],
                "rubric_item": number,
                "criterion": rubric["criterion"],
                "axis": rubric.get("axe") or rubric.get("axis") or "Unspecified",
                "points": rubric["points"],
                "judge_gpt": evaluation["weighted_score"],
            }
            for i, physician in enumerate(physicians):
                record[physician] = physician_data.at[i, physician_columns[key]]
            rows.append(record)

    df = pd.DataFrame(rows).sort_values(["case_id", "rubric_item"]).reset_index(drop=True)
    df.to_excel(OUTPUT_DIR / "02_scores_combined.xlsx", index=False)

    # The rubric grading is binary: each score should be either zero or its signed weight.
    for judge in ["judge_gpt"] + physicians:
        df[judge] = pd.to_numeric(df[judge], errors="raise")
        bad = df[judge].notna() & (df[judge] != 0) & (df[judge] != df["points"])
        if bad.any():
            raise ValueError(f"Unexpected scores in {judge}; expected 0 or signed 'points'.")

    # Met = criterion triggered. For a negative criterion, this means the bad behavior occurred.
    for judge in ["judge_gpt"] + physicians:
        df[judge + "_met"] = df[judge].apply(
            lambda value: pd.NA if pd.isna(value) else int(value != 0)
        ).astype("Int64")
    df.to_excel(OUTPUT_DIR / "03_binary_met.xlsx", index=False)
    return df, physicians


# --------------------------- Step 2: Macro F1 ---------------------------
def calculate_mf1(comparisons):
    """Macro F1 = mean(F1 for Met, F1 for Not Met); no consensus voting."""
    predicted = comparisons["pred_met"]
    truth = comparisons["reference_met"]
    tp = int(((predicted == 1) & (truth == 1)).sum())
    tn = int(((predicted == 0) & (truth == 0)).sum())
    fp = int(((predicted == 1) & (truth == 0)).sum())
    fn = int(((predicted == 0) & (truth == 1)).sum())

    # Like the HealthBench implementation, undefined class precision/recall means undefined F1.
    f1_met = (2 * tp / (2 * tp + fp + fn)) if (tp + fp) and (tp + fn) else float("nan") # F1 score positive class
    f1_not_met = (2 * tn / (2 * tn + fp + fn)) if (tn + fn) and (tn + fp) else float("nan")
    return {
        "n_comparisons": len(comparisons), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "f1_met": f1_met, "f1_not_met": f1_not_met,
        "macro_f1": (f1_met + f1_not_met) / 2,
    }


def run_analysis(df, physicians):
    pairs = []
    for _, row in df.iterrows():
        common = {
            "case_id": row["case_id"], "rubric_item": row["rubric_item"],
            "model": row["model"], "axis": row["axis"], "points": row["points"],
        }
        for physician in physicians:
            for other in physicians:
                if physician != other and pd.notna(row[physician + "_met"]) and pd.notna(row[other + "_met"]):
                    pairs.append({**common, "rater": physician, "reference": other,
                                  "pred_met": int(row[physician + "_met"]),
                                  "reference_met": int(row[other + "_met"])})
            if pd.notna(row["judge_gpt_met"]) and pd.notna(row[physician + "_met"]):
                pairs.append({**common, "rater": "judge_gpt", "reference": physician,
                              "pred_met": int(row["judge_gpt_met"]),
                              "reference_met": int(row[physician + "_met"])})

    pairs = pd.DataFrame(pairs)
    pairs.to_excel(OUTPUT_DIR / "04_pairwise_comparisons.xlsx", index=False)

    # Pool individual comparisons first; then average physician MF1 scores.
    summary = []
    for axis in ["All"] + sorted(df["axis"].dropna().unique().tolist()): # it does first all together and then one axis at the time
        by_axis = pairs if axis == "All" else pairs[pairs["axis"] == axis]
        for rater in physicians + ["judge_gpt"]:
            subset = by_axis[by_axis["rater"] == rater]
            if subset.empty:
                continue
            summary.append({"axis": axis, "rater": rater, **calculate_mf1(subset)})

        # Arithmetic mean is appropriate when all physicians grade the same items.
        individual = [r["macro_f1"] for r in summary if r["axis"] == axis and r["rater"] in physicians]
        summary.append({"axis": axis, "rater": "physician_mean",
                        "macro_f1": pd.Series(individual).mean() if individual else float("nan")})

    summary = pd.DataFrame(summary)
    summary.to_excel(OUTPUT_DIR / "05_macro_f1.xlsx", index=False)
    print("\nMacro F1 (all axes):")
    print(summary.loc[summary["axis"] == "All", ["rater", "n_comparisons", "macro_f1"]].to_string(index=False))



# --------------------------- Step 3: Case-level correlation ---------------------------
def run_case_correlation(df, physicians):

    rows = []

    # Calculate case scores overall and separately by medical axis.
    groups = [("All", df)] + [
        (axis, df[df["axis"] == axis])
        for axis in sorted(df["axis"].dropna().unique())
    ]

    for axis, data in groups:
        for (case_id, model), case in data.groupby(["case_id", "model"]):

            # Maximum possible score: sum of positive rubric weights.
            max_score = case.loc[case["points"] > 0, "points"].sum()

            record = {"axis": axis, "case_id": case_id, "model": model}

            # Calculate a normalized score for GPT and each physician.
            for judge in ["judge_gpt"] + physicians:
                values = case[judge]

                if max_score > 0 and values.notna().all():
                    score = values.sum() / max_score
                    record["s_" + judge] = max(0, min(1, score))
                else:
                    record["s_" + judge] = float("nan")

            # Human consensus: average physician case scores.
            human_scores = [record["s_" + p] for p in physicians]

            record["s_human"] = (
                sum(human_scores) / len(human_scores)
                if all(pd.notna(x) for x in human_scores)
                else float("nan")
            )

            record["s_rubric"] = record["s_judge_gpt"]
            rows.append(record)

    # Save all individual case scores for inspection.
    case_scores = pd.DataFrame(rows)
    case_scores.to_excel(
        OUTPUT_DIR / "06_case_level_scores.xlsx", index=False
    )

    # Calculate Pearson correlation across cases, overall and by axis.
    correlations = []

    for axis, data in case_scores.groupby("axis", sort=False):
        valid = data[["s_rubric", "s_human"]].dropna()

        if (len(valid) >= 3
                and valid["s_rubric"].nunique() > 1
                and valid["s_human"].nunique() > 1):
            rho, p_value = pearsonr(valid["s_rubric"], valid["s_human"])
        else:
            rho, p_value = float("nan"), float("nan")

        correlations.append({
            "axis": axis,
            "n_cases": len(valid),
            "pearson_r": rho,
            "p_value": p_value
        })

    correlation_df = pd.DataFrame(correlations)
    correlation_df.to_excel(
        OUTPUT_DIR / "07_case_correlations.xlsx", index=False
    )

    print("\nCase-level Pearson correlations:")
    print(correlation_df.to_string(index=False))


if __name__ == "__main__":
    scores, physicians = prepare_scores()
    run_analysis(scores, physicians)
    run_case_correlation(scores, physicians)
    print(f"\nSaved 5 files to: {OUTPUT_DIR}")
