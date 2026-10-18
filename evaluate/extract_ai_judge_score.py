import json
import pandas as pd

files = {
    "Doximity Ask Instant": "./../outputs/LB/evaluation_results_input_Doximity_Ask_Instant_2026-09-10.json",
    "Doximity Ask Thinking": "./../outputs/LB/evaluation_results_input_Doximity_Ask_Thinking_2026-09-10.json",
    "OpenEvidence Sackett": "./../outputs/LB/evaluation_results_input_OpenEvidence_Regular_2026-09-10.json",
    "GPT52": "./../outputs/gpt52_1/evaluation_results_gpt52_1.json",
}

# Read selected case/model combinations
selections = pd.read_excel("./../data/subset-livemedbench/cases_40.xlsx")

# Load JSON evaluations
results = {}
for model, path in files.items():
    with open(path) as f:
        results[model] = {
            int(x["case_id"]): x["evaluations"]
            for x in json.load(f)
        }

# Extract selected rubric scores
rows = []
for _, row in selections.iterrows():
    case = int(row["case_id"])
    model = row["model"]

    for rubric, evaluation in results[model][case].items():
        rows.append([
            case,
            int(rubric.split("_")[-1]) - 1,
            evaluation["weighted_score"],
            model
        ])

# Export to Excel
df = pd.DataFrame(
    rows,
    columns=["Case", "Rubric item", "AI judge score", "Model used"]
)

df.to_excel("./../outputs/analysis/ai_judge_scores.xlsx", index=False)