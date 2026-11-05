"""Step 1: Collect scores, rubric judgments, and response-text metadata.

Place these scripts in LiveMedBench/evaluate/ and run from anywhere.
Existing evaluation files are read only; outputs go to outputs/analysis/research/.
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/analysis/research"

# These are the eight runs documented in Per Case Output.ipynb.
# user = person who generated the model response; run = repetition of GPT-as-judge.
RUNS = {
    "LB": [(1, "LB"), (2, "LB2"), (1, "gpt52_1"), (2, "gpt52_12")],
    "SJ": [(1, "SJ"), (2, "SJ2"), (1, "gpt52_2"), (2, "gpt52_22")],
}


def model_name(name):
    """Give the same model the same label across files and users."""
    name = re.sub(r"^evaluation_results_", "", str(name))
    name = re.sub(r"^input_", "", name)
    name = re.sub(r"_2026-.*$", "", name).replace("_", " ").strip()
    if name.lower().startswith(("gpt52", "gpt 52", "gpt-5.2", "gpt 5.2")):
        return "GPT52"
    if name.lower() in ("openevidence sackett", "openevidence regular"):
        return "OpenEvidence Regular"
    return name


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rubric_paths = [
        ROOT / "data/Subset_LiveMedBench_v202604_new.json",
        ROOT / "data/subset-livemedbench/Subset_LiveMedBench_v202604_new.json",
    ]
    rubric_file = next((p for p in rubric_paths if p.exists()), None)
    if rubric_file is None:
        print("WARNING: rubric JSON not found; axis/rubric analyses will be unavailable.")
        rubric = {}
    else:
        rubric = {str(x["case_id"]): x["rubric_items"] for x in read_json(rubric_file)}

    scores, judgments, text_rows = [], [], []
    for user, runs in RUNS.items():
        for judge_run, folder in runs:
            directory = ROOT / "outputs" / folder
            score_path = directory / "metric_all.json"
            if not score_path.exists():
                print(f"Skipping missing scores: {score_path}")
                continue

            for raw_model, cases in read_json(score_path).items():
                model = model_name(raw_model)
                for case_id, entry in cases.items():
                    scores.append({
                        "user": user, "judge_run": judge_run, "model": model,
                        "case_id": str(case_id), "score": entry.get("score"),
                        "post_time": entry.get("post_time"), "source_dir": folder,
                    })

            # The rubric file links rubric_1 to its clinical axis and weight.
            for path in directory.glob("evaluation_results_*.json"):
                model = model_name(path.stem)
                for case in read_json(path):
                    case_id = str(case["case_id"])
                    items = rubric.get(case_id, [])
                    for rubric_key, result in case.get("evaluations", {}).items():
                        match = re.fullmatch(r"rubric_(\d+)", rubric_key)
                        if not match or not items:
                            continue
                        number = int(match.group(1))
                        if not (1 <= number <= len(items)):
                            continue
                        points = items[number - 1].get("points", 0)
                        met = result.get("score")
                        if met not in (0, 1) or points == 0:
                            continue
                        axis = items[number - 1].get("axe") or items[number - 1].get("axis")
                        if not axis:
                            continue
                        judgments.append({
                            "user": user, "judge_run": judge_run, "model": model,
                            "case_id": case_id, "rubric_item": number, "axis": axis,
                            "points": points, "met": met,
                            # 'Met' on a negative criterion means the harmful behavior occurred.
                            "error": int((points > 0 and met == 0) or (points < 0 and met == 1)),
                        })

            # Optional: GPT52 summary may not exist yet. Missing does not mean 0 words.
            summary_path = directory / "analysis_summary.json"
            if summary_path.exists():
                for item in read_json(summary_path):
                    text_rows.append({
                        "user": user, "judge_run": judge_run,
                        "model": model_name(item["model"]),
                        "case_id": str(item["case_id"]),
                        "word_count": item.get("main_text_word_count"),
                        "reference_count": item.get("total_reference_count"),
                        "average_reference_year": item.get("average_publication_year"),
                        "has_references_heading": item.get("references_found_heading"),
                        "source_domain_flag": item.get("contains_source_domain"),
                        "flagged_domains": ", ".join(item.get("flagged_domains") or []),
                    })

    columns = {
        "case_scores.csv": ["user", "judge_run", "model", "case_id", "score", "post_time", "source_dir"],
        "rubric_judgments.csv": ["user", "judge_run", "model", "case_id", "rubric_item", "axis", "points", "met", "error"],
        "text_metrics.csv": ["user", "judge_run", "model", "case_id", "word_count", "reference_count",
                             "average_reference_year", "has_references_heading", "source_domain_flag", "flagged_domains"],
    }
    for name, data in [("case_scores.csv", scores),
                       ("rubric_judgments.csv", judgments),
                       ("text_metrics.csv", text_rows)]:
        pd.DataFrame(data, columns=columns[name]).to_csv(OUT / name, index=False)
        print(f"Saved {name}: {len(data)} rows")

    if judgments:
        grouped = ["user", "judge_run", "model", "case_id", "axis"]
        axis_df = (pd.DataFrame(judgments).groupby(grouped, as_index=False)
                   .agg(errors=("error", "sum"), n_criteria=("error", "size")))
        axis_df["error_rate"] = axis_df["errors"] / axis_df["n_criteria"]
        axis_df["accuracy"] = 1 - axis_df["error_rate"]
        axis_df.to_csv(OUT / "axis_errors.csv", index=False)
        print(f"Saved axis_errors.csv: {len(axis_df)} rows")
    else:
        print("No rubric-level results found; axis_errors.csv not generated.")


if __name__ == "__main__":
    main()
