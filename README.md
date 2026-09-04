# Evaluation of Subset Data from LiveMedBench using Specialized Models

This repository focuses on running and evaluating specialized models on a subset of LiveMedBench data.

---

## Repository Structure

```text
LiveMedBench/
  evaluate/
    run_model.py           # Run an LLM on a subset of LiveMedBench cases
    evaluate_model.py      # Use GPT-4.1 as a rubric-based grader
    metric_calc.py         # Aggregate scores and compute metrics
  fig/                     # Figures for documentation
  data/                    # Benchmark and subset input data
  outputs/                 # (Recommended) folder for model outputs and evaluations
  requirements.txt         # Python dependencies
  LICENSE                  # MIT License
```

---

## Quick Start

### 0. Create 100-case subset dataset

This create the dataset with 100 cases

```bash
python pipeline/prepare_subset.py \
--cases-file ./data/subset-livemedbench/cases-to-consider.xlsx \
--input-file ./data/LiveMedBench_v202604_new.json \
--output-file ./data/subset-livemedbench/Subset_LiveMedBench_v202604_new.json
```

This generates a json file per model

```bash
python pipeline/sheet_to_json.py \
--input-csv ./data/LiveMedBench\ Study\ \(Responses\)\ -\ Form\ Responses.csv \
--subset-file ./data/subset-livemedbench/Subset_LiveMedBench_v202604_new.json \
--output-dir ./outputs/ --run-date <YYYY-MM-DD>
```

### 1. Environment Setup

```bash
conda create -n livemedbench python=3.10 -y
conda activate livemedbench
pip install -r requirements.txt
```

Set your OpenAI API key:

```bash
export OPENAI_API_KEY="sk-..."  # DO NOT hard-code this in code
```

### 2. Download Data

Place the required benchmark and response files under the `data/` directory (including the subset inputs used in this repository).

### 3. Run Models on LiveMedBench

```bash
python evaluate/run_model.py \
  --data-file data/LiveMedBench_v202601.json \
  --output-file outputs/gpt_results.json \
  --model gpt-5.2-2025-12-11
```

Key arguments:
- `--data-file`: Path to a JSON list of cases.
- `--output-file`: Where to save model outputs.
- `--model`: Any OpenAI-compatible chat model name.
- `--max-cases` (optional): Limit the number of processed cases.
- `--resume` (optional): Resume from an existing output file by `case_id`.

### 4. Rubric-based Evaluation with GPT-4.1

```bash
python evaluate/evaluate_model.py \
  --rubric-file data/LiveMedBench_v202601.json \
  --model-result-file outputs/gpt_results.json \
  --output-file outputs/evaluation_results_gpt.json \
  --response-field model_response \
  --resume (optional)
```

### 5. Compute Metrics

```bash
python evaluate/metric_calc.py \
  --rubric-file data/LiveMedBench_v202601.json \
  --evaluation-dir outputs \
  --output-file outputs/metric_results.txt
```

```bash
python evaluate/metric_calc_by_ax_caseid.py --rubric-file data/subset-livemedbench/Subset_LiveMedBench_v202604_new.json --evaluation-dir outputs --output-file outputs/metrics-by_ax_per_case_<modelname>_<YYYY-MM-DD>.json
```

---

## Data Format

Each case in the rubric-augmented dataset has the following structure:

```json
{
  "case_id": "1",
  "post_time": "2023-04-16T00:00:00",
  "narrative": "A 45-year-old male presents with...",
  "core_request": "What could be causing these symptoms?",
  "doctor_advice": "Based on the symptoms described...",
  "rubric_items": [
    {
      "criterion": "Does the model identify the likely cause as Norovirus?",
      "points": 10
    },
    {
      "criterion": "Does the model incorrectly recommend antibiotics?",
      "points": -5
    }
  ]
}
```

- **Positive `points`**: Reward for including correct clinical information.
- **Negative `points`**: Penalty for hallucinations, contraindications, or safety risks.
- The final per-case score is `clip(sum(weighted_scores) / sum(positive_points), 0, 1)`.

---

## License

This project is licensed under the [MIT License](LICENSE). See the `LICENSE` file for details.

The benchmark data is intended solely for **research evaluation**. It must not be treated as medical advice, used for self-diagnosis or treatment planning, or used for training clinical deployment models without regulatory validation.
