#!/usr/bin/env python3

import argparse
import glob
import json
import pandas as pd
from collections import defaultdict
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rubric-file", required=True)
    parser.add_argument("--evaluation-dir", required=True)
    parser.add_argument(
        "--output-file",
        default="metric_results_by_axis_per_case.txt",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():

    args = parse_args()

    # ---------------------------------------------------------
    # Load rubric
    # ---------------------------------------------------------

    rubric_data = load_json(args.rubric_file)

    rubric_by_case = {}

    for case in rubric_data:
        rubric_by_case[str(case["case_id"])] = case


    # Find all axes automatically
    axes_set = set()

    for case in rubric_data:
        for item in case.get("rubric_items", []):
            if "axe" in item:
                axes_set.add(item["axe"])

    axes = sorted(axes_set)

    print("Axes found:")
    for axe in axes:
        print(f"  - {axe}")


    # ---------------------------------------------------------
    # Find evaluation files
    # ---------------------------------------------------------

    pattern = str(
        Path(args.evaluation_dir) / "evaluation_results_*.json"
    )

    evaluation_files = glob.glob(pattern)

    if not evaluation_files:
        print("No evaluation files found.")
        return


    # ---------------------------------------------------------
    # Results structure:
    #
    # model -> case_id -> axe -> {"errors": X, "total": Y}
    # ---------------------------------------------------------

    results = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: {"errors": 0, "total": 0}
            )
        )
    )

    post_times = {}


    # ---------------------------------------------------------
    # Process each model
    # ---------------------------------------------------------

    for file_path in evaluation_files:

        filename = Path(file_path).name

        model_name = filename[
            len("evaluation_results_") : -len(".json")
        ]

        print(f"\nProcessing {model_name}")

        evaluations = load_json(file_path)

        for case_eval in evaluations:

            case_id = str(case_eval["case_id"])

            if case_id not in rubric_by_case:
                continue

            rubric_case = rubric_by_case[case_id]

            rubric_items = rubric_case["rubric_items"]

            post_times[case_id] = rubric_case.get("post_time", "")


            # -------------------------------------------------
            # Examine each evaluated rubric item
            # -------------------------------------------------

            for rubric_key, evaluation in case_eval.get(
                "evaluations", {}
            ).items():

                # rubric_1 -> index 0
                try:
                    rubric_number = int(
                        rubric_key.split("_")[1]
                    )

                    rubric_item = rubric_items[rubric_number - 1]

                except (IndexError, ValueError):
                    continue


                axe = rubric_item.get("axe")
                points = rubric_item.get("points", 0)
                score = evaluation.get("score")


                if axe is None:
                    continue

                if score not in (0, 1):
                    continue

                if points == 0:
                    continue


                # Every criterion counts once
                results[model_name][case_id][axe]["total"] += 1


                # -------------------------------------------------
                # ERROR definition
                #
                # Positive criterion:
                #     score 0 = error
                #
                # Negative criterion:
                #     score 1 = error
                # -------------------------------------------------

                error = (
                    (points > 0 and score == 0)
                    or
                    (points < 0 and score == 1)
                )


                if error:
                    results[model_name][case_id][axe]["errors"] += 1


    # ---------------------------------------------------------
    # Write results
    # ---------------------------------------------------------

    output_path = Path(args.output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    with open(output_path, "w", encoding="utf-8") as f:

        header = [
            "Case ID",
            "Model",
            "Post Time",
            *axes,
        ]

        f.write("\t".join(header) + "\n")
        rows = []   

        for model_name in sorted(results):

            for case_id in sorted(
                results[model_name],
                key=lambda x: int(x)
            ):

                # row = [
                #    case_id,
                #     model_name,
                #     post_times.get(case_id, ""),
                # ]
                row = {"Case ID": case_id, 
                       "Model": model_name, 
                       "Post Time": post_times.get(case_id, "")
                       }


                for axe in axes:

                    data = results[model_name][case_id][axe]

                    if data["total"] > 0:

                        error_rate = (
                            data["errors"] /
                            data["total"]
                        )
                        row[axe] = round(error_rate, 4)
                        
                        # row.append(
                        #    f"{error_rate:.4f}"
                        # )

                    else:

                        # This case has no criteria
                        # belonging to this axis
                        # row.append("NA")
                        row[axe] = None

                rows.append(row)
                # f.write("\t".join(row) + "\n")

    # ---------------------------------------------------------
    # Save as CSV
    # ---------------------------------------------------------

    df_results = pd.DataFrame(rows)

    output_path = Path(args.output_file)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df_results.to_csv(
        output_path,
        index=False
    )

    print(f"\nResults saved to: {output_path}")

    print(
        f"\nResults saved to: {output_path}"
    )


if __name__ == "__main__":
    main()