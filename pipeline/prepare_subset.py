#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STAGE 1 — Subset preparation.

Direct port of `Select Cases of Interest.ipynb`. The filtering operations are
reproduced exactly as written in the notebook; nothing has been added,
removed, or reordered.

Notebook cell being reproduced:

    input_file = "LiveMedBench_v202604_new.json"
    output_file = "Subset_LiveMedBench_v202604_new.json"
    selected_case_ids = set(df_selected["case_id"].tolist())
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    filtered_data = [
        case
        for case in data
        if case["case_id"] in selected_case_ids
    ]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(filtered_data)} cases to {output_file}")

Usage:
    python3 pipeline/prepare_subset.py \
        --cases-file data/cases-to-consider.xlsx \
        --input-file data/LiveMedBench_v202604_new.json \
        --output-file data/Subset_LiveMedBench_v202604_new.json
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter the full LiveMedBench dataset down to the cases "
                    "listed in cases-to-consider.xlsx."
    )
    parser.add_argument("--cases-file", required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-file", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df_selected = pd.read_excel(args.cases_file)

    input_file = args.input_file
    output_file = args.output_file

    # Case IDs you want to keep
    selected_case_ids = set(df_selected["case_id"].tolist())

    # Load original JSON
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Keep only selected cases
    filtered_data = [
        case
        for case in data
        if case["case_id"] in selected_case_ids
    ]

    # Save filtered JSON
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(filtered_data)} cases to {output_file}")


if __name__ == "__main__":
    main()
