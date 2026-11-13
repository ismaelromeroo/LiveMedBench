# Evaluation of Subset Data from LiveMedBench using Specialized Models

This repository focuses on running and evaluating specialized clinical AI models on a subset of LiveMedBench data. In addition to generating model responses and rubric-based scores, the repository includes a research-analysis pipeline for evaluating score reproducibility, rubric-level stability, performance by clinical axis, response length and reference behavior, and agreement between an AI judge and physician judges.

---

## Repository Structure

```text
LiveMedBench/
  pipeline/
    prepare_subset.py              # Create the 100-case LiveMedBench subset
    sheet_to_json.py               # Convert collected model responses to JSON

  evaluate/
    run_model.py                   # Run an LLM on a subset of LiveMedBench cases
    evaluate_model.py              # Apply rubric-based AI grading
    metric_calc.py                 # Aggregate rubric scores into model/case metrics
    metric_calc_by_ax_caseid.py    # Compute metrics by clinical axis and case

    prepare.py                     # Build analysis-ready research datasets
    stability_axes.py              # Reproducibility, model comparison, and axis analyses
    references_length.py           # References, publication year, length, and performance
    clinical_AI_judges.py          # Compare AI-judge and physician rubric judgments

  data/                            # Benchmark, subset, and physician-rating inputs
  outputs/                         # Model outputs and rubric evaluations
    analysis/
      research/                    # Outputs from prepare/stability/references analyses
  fig/                             # Figures for documentation
  requirements.txt                 # Python dependencies
  LICENSE                          # MIT License
```

---

## Quick Start

### 0. Create the 100-case subset dataset

Create the subset used for the study:

```bash
python pipeline/prepare_subset.py \
  --cases-file ./data/subset-livemedbench/cases-to-consider.xlsx \
  --input-file ./data/LiveMedBench_v202604_new.json \
  --output-file ./data/subset-livemedbench/Subset_LiveMedBench_v202604_new.json
```

Convert collected model responses into one JSON file per model:

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

Place the required benchmark and response files under the `data/` directory, including the subset inputs used in this repository.

### 3. Run Models on LiveMedBench

```bash
python evaluate/run_model.py \
  --data-file data/LiveMedBench_v202601.json \
  --output-file outputs/gpt_results.json \
  --model gpt-5.2-2025-12-11
```

Key arguments:

- `--data-file`: path to a JSON list of cases.
- `--output-file`: where to save model outputs.
- `--model`: OpenAI-compatible model name.
- `--max-cases` (optional): limit the number of processed cases.
- `--resume` (optional): resume from an existing output file by `case_id`.

### 4. Rubric-based Evaluation

```bash
python evaluate/evaluate_model.py \
  --rubric-file data/LiveMedBench_v202601.json \
  --model-result-file outputs/gpt_results.json \
  --output-file outputs/evaluation_results_gpt.json \
  --response-field model_response \
  --resume
```

The evaluation output contains one binary rubric judgment per criterion. The corresponding `weighted_score` is either `0` or the signed rubric weight.

### 5. Compute Metrics

```bash
python evaluate/metric_calc.py \
  --rubric-file data/LiveMedBench_v202601.json \
  --evaluation-dir outputs \
  --output-file outputs/metric_results.txt
```

Metrics can also be calculated by clinical axis and case:

```bash
python evaluate/metric_calc_by_ax_caseid.py \
  --rubric-file data/subset-livemedbench/Subset_LiveMedBench_v202604_new.json \
  --evaluation-dir outputs \
  --output-file outputs/metrics-by_ax_per_case_<modelname>_<YYYY-MM-DD>.json
```

---

# Research Analysis Pipeline

The research-analysis scripts address four related questions:

1. Are model-level and rubric-level results reproducible when the same responses are judged more than once?
2. Are the results reproducible across independently generated evaluation runs/users (`LB` and `SJ`)?
3. Do models differ in overall performance or in errors within specific clinical evaluation axes?
4. Are response characteristics such as length, references, and publication year associated with performance, and how closely does the AI judge agree with physician judges?

The main analysis sequence is:

```text
prepare.py
    |
    +--> stability_axes.py
    |
    +--> references_length.py

clinical_AI_judges.py    # separate physician-validation branch
```

The first three scripts use `outputs/analysis/research/`. `clinical_AI_judges.py` performs a separate physician-validation analysis and writes to `outputs/analysis/`.

The hypotheses below describe the statistical questions implemented by the scripts. They should not be called preregistered hypotheses unless they were formally preregistered elsewhere.

---

## 6. `prepare.py` — Build Analysis-Ready Research Tables

### Purpose

`prepare.py` is the data-preparation layer for the research analyses. It does not perform inferential hypothesis testing. It harmonizes repeated model-evaluation runs and converts raw JSON outputs into case-level, rubric-level, axis-level, and response-metadata tables.

The script currently recognizes two independent response/evaluation groups, `LB` and `SJ`, and two repetitions of the GPT-as-judge evaluation. It normalizes model names so that the same model is represented consistently across runs.

### Research role

The script prepares the data required to test:

- repeatability of GPT-as-judge scores;
- reproducibility between LB and SJ;
- stability of individual rubric decisions;
- differences in error burden across clinical axes;
- associations between output characteristics and performance.

No p-values or formal hypothesis tests are produced by `prepare.py` itself.

### Inputs

The script reads:

- `metric_all.json` from each configured evaluation directory;
- `evaluation_results_*.json` files containing rubric-level AI judgments;
- `Subset_LiveMedBench_v202604_new.json`, which maps each `rubric_n` item to its clinical axis and signed point weight;
- optional `analysis_summary.json` files containing response-level metadata such as word count and references.

If an `analysis_summary.json` file is absent, reference and length variables remain missing. Missing metadata are **not** interpreted as zero references or zero words.

### Derived rubric variables

For every rubric item, `prepare.py` records the binary `met` judgment and derives an `error` variable.

For a **positive** criterion (`points > 0`):

```text
met = 1  -> expected criterion satisfied -> error = 0
met = 0  -> expected criterion missed    -> error = 1
```

For a **negative** criterion (`points < 0`):

```text
met = 1  -> undesirable behavior occurred -> error = 1
met = 0  -> undesirable behavior avoided  -> error = 0
```

This distinction is essential: for a negative criterion, `met = 1` means that the penalized behavior occurred.

### Outputs

All files are written to:

```text
outputs/analysis/research/
```

#### `case_scores.csv`

One row per user × judge run × model × case.

Key fields:

- `user`: independent response/evaluation group (`LB` or `SJ`);
- `judge_run`: GPT-as-judge repetition (`1` or `2`);
- `model`: normalized model name;
- `case_id`: case identifier;
- `score`: case-level score read from `metric_all.json`;
- `post_time`: original case date/time when available;
- `source_dir`: source output directory.

The score is retained as stored in `metric_all.json`; `prepare.py` does not re-scale or re-clip it.

#### `rubric_judgments.csv`

One row per user × judge run × model × case × rubric item.

Key fields:

- `rubric_item`;
- `axis`;
- `points`;
- `met`;
- `error`.

This is the main input for rubric-level reproducibility analyses.

#### `text_metrics.csv`

One row per user × judge run × model × case when text metadata are available.

Fields include:

- `word_count`;
- `reference_count`;
- `average_reference_year`;
- `has_references_heading`;
- `source_domain_flag`;
- `flagged_domains`.

These variables are used by `references_length.py`.

#### `axis_errors.csv`

One row per user × judge run × model × case × axis.

Rubric-item errors are aggregated within each axis:

```text
error_rate = errors / n_criteria
accuracy   = 1 - error_rate
```

Fields include:

- `errors`;
- `n_criteria`;
- `error_rate`;
- `accuracy`.

This is the main axis-level input to `stability_axes.py`.

### Run

```bash
python evaluate/prepare.py
```

---

## 7. `stability_axes.py` — Reproducibility, Model Comparison, and Clinical-Axis Analysis

### Purpose

`stability_axes.py` evaluates whether benchmark conclusions are stable across repeated GPT-as-judge runs and across the two independent evaluation groups. It also summarizes model performance, tests whether models differ on the same cases, and examines error patterns by clinical axis.

All comparisons are matched by identifiers such as model, case, and rubric item rather than by row position.

### Hypothesis 1: GPT-as-judge repeatability

**Research question:** If the same model responses are evaluated twice by the GPT judge, are the resulting scores and rubric decisions reproducible?

For each user and model, judge run 1 is paired with judge run 2 on the same cases.

- **H0:** There is no systematic difference between judge run 1 and judge run 2.
- **H1:** The repeated judge runs differ systematically.

The script reports:

- number of paired observations;
- mean signed difference;
- mean absolute difference;
- exact agreement;
- Pearson correlation;
- paired Wilcoxon signed-rank p-value.

For binary rubric judgments, it additionally reports:

- F1 for `met`;
- F1 for `not met`;
- Macro F1;
- Cohen's kappa.

High exact agreement/Macro F1 and small absolute differences support repeatability. Correlation alone should not be interpreted as agreement.

### Hypothesis 2: LB-versus-SJ reproducibility

**Research question:** When LB and SJ independently run the same model/evaluation workflow, do they obtain comparable results on the same cases?

For each model and GPT-judge repetition, LB and SJ are paired on matching case IDs and, for rubric analyses, matching rubric items.

- **H0:** There is no systematic LB-versus-SJ difference.
- **H1:** LB and SJ produce systematically different scores or rubric decisions.

The same paired-difference and agreement statistics are reported.

### Hypothesis 3: Differences in model performance

**Research question:** Do the evaluated models achieve different case-level scores when tested on the same cases?

Because the models are evaluated on matched cases, the script uses a **Friedman test**.

- **H0:** The models have the same distribution of within-case ranks/performance.
- **H1:** At least one model differs from the others.

The script reports:

- models included;
- number of common cases;
- Friedman statistic;
- p-value.

A significant Friedman test establishes an overall difference but does not identify which model pairs differ. Post-hoc pairwise testing would be required for that conclusion.

### Hypothesis 4: Stability and performance by clinical axis

**Research question:** Are rubric decisions and axis-level error rates stable across repeated judging and across LB/SJ, and which clinical axes show the highest error burden?

Axis-level analyses are descriptive and reproducibility-oriented. For each axis, the script summarizes error rate and accuracy and repeats the paired stability comparisons.

### Outputs

All files are written to:

```text
outputs/analysis/research/
```

#### `score_summary.csv`

Descriptive case-level performance for each user × judge run × model:

- `n_cases`;
- `mean_score`;
- `sd_score`;
- `ci95_low`;
- `ci95_high`.

The confidence interval is a 95% t interval around the mean.

#### `case_score_stability.csv`

Case-level reproducibility results for:

- GPT judge run 1 vs run 2;
- LB vs SJ.

Includes paired differences, exact agreement, Pearson correlation, and Wilcoxon p-values.

#### `model_comparison_friedman.csv`

Matched-case omnibus model comparison for each user and judge run.

Fields include:

- models included;
- number of common cases;
- Friedman statistic;
- p-value.

#### `rubric_met_stability.csv`

Overall reproducibility of binary rubric-item judgments.

Additional fields include:

- `f1_met`;
- `f1_not_met`;
- `macro_f1`;
- `cohen_kappa`.

#### `rubric_stability_by_axis.csv`

Rubric-level agreement stratified by clinical axis.

This is useful for identifying axes for which the AI judge is more or less reproducible.

#### `axis_summary.csv`

Descriptive error burden for each user × judge run × model × axis:

- number of unique cases;
- total number of rubric criteria;
- mean case-level error rate;
- mean case-level accuracy.

#### `axis_error_stability.csv`

Paired reproducibility of case-level axis error rates for:

- GPT judge run 1 vs run 2;
- LB vs SJ.

### Run

`prepare.py` must be run first.

```bash
python evaluate/stability_axes.py
```

---

## 8. `references_length.py` — Response Length, References, Publication Year, and Performance

### Purpose

`references_length.py` evaluates whether observable characteristics of the generated answers are associated with case-level benchmark performance.

To avoid counting the same model response twice solely because it was judged twice, this analysis uses **judge run 1 only**.

### Hypothesis 1: Response length and performance

**Research question:** Is response length associated with benchmark score?

- **H0:** Response word count is not associated with case-level score.
- **H1:** Response word count is associated with case-level score.

The script reports Pearson and Spearman correlations. Unless a direction was specified prospectively, this should be interpreted as a two-sided/exploratory association rather than as a claim that longer responses are necessarily better.

### Hypothesis 2: Number of references and performance

**Research question:** Are responses containing more references associated with benchmark performance?

- **H0:** Reference count is not associated with score.
- **H1:** Reference count is associated with score.

The script distinguishes **zero references** from **missing reference metadata**.

### Hypothesis 3: Reference recency and performance

**Research question:** Is average reference publication year associated with benchmark performance?

- **H0:** Average reference publication year is not associated with score.
- **H1:** Average reference publication year is associated with score.

A positive association would indicate that responses citing more recent literature tend to score higher, but this analysis is correlational and does not establish causation.

### Analysis subsets

Correlations are calculated for:

1. `all_responses`;
2. `with_references`, restricted to `reference_count >= 1`.

Results are generated for:

- all models and both users pooled;
- each user pooled across models;
- each model pooled across users;
- each user × model combination.

### Statistical outputs

For every predictor, the script reports:

- sample size used in the correlation;
- Pearson `r` and p-value;
- Spearman `rho` and p-value;
- number of responses in the group;
- number with missing predictor values.

Pearson evaluates linear association. Spearman evaluates monotonic association and is less dependent on linearity.

### Dependence caveat

The pooled LB/SJ analyses treat rows as independent when calculating p-values, even though LB and SJ share cases. Pooled inferential p-values should therefore be interpreted cautiously. A clustered or mixed-effects analysis would be preferable if formal pooled inference is required.

### Outputs

All files are written to:

```text
outputs/analysis/research/
```

#### `length_reference_case_data.csv`

Analysis-ready case-level dataset created by merging judge-run-1 scores with text/reference metadata.

This file is useful for inspection, plotting, and alternative statistical models.

#### `reference_length_summary.csv`

Descriptive statistics by user × model:

- number of available scores;
- number of responses with length metadata;
- number with reference metadata;
- number with zero references;
- mean and SD word count;
- mean and SD reference count;
- mean and SD publication year;
- number of responses containing a references heading;
- number of source-domain flags.

#### `performance_correlations.csv`

Correlation results for each analysis subset, grouping level, model, and predictor.

Predictors:

- `word_count`;
- `reference_count`;
- `average_reference_year`.

### Run

`prepare.py` must be run first.

```bash
python evaluate/references_length.py
```

---

## 9. `clinical_AI_judges.py` — AI-Judge Agreement with Physician Judges

### Purpose

`clinical_AI_judges.py` evaluates whether rubric judgments made by the AI judge agree with physician judgments and places AI-physician agreement in the context of physician-physician agreement.

This analysis is performed on the selected case/model pairs in `cases_40.xlsx`. It is a separate validation branch and does not require `prepare.py`.

### Primary research hypothesis

**Research question:** How closely does the AI rubric judge reproduce physician judgments, and is that level of agreement comparable to physician-physician agreement?

The principal descriptive hypothesis is:

- **H1:** AI-physician agreement, measured by Macro F1, approaches the physician-physician agreement observed on the same rubric items.

The script does not perform a formal significance test comparing AI-physician and physician-physician Macro F1. Differences should therefore be reported descriptively unless an additional inferential procedure is added.

### Secondary hypothesis: agreement by clinical axis

**Research question:** Does AI-physician agreement vary across clinical evaluation axes?

Macro F1 is calculated across all axes and separately within each axis.

### Inputs

The script reads:

- `data/subset-livemedbench/cases_40.xlsx`: selected `case_id` and `model` pairs;
- `data/AI_Clinical_Tool_Evaluation_Data.xlsx`: physician rubric ratings;
- `data/Subset_LiveMedBench_v202604_new.json`: rubric criterion, axis, and signed point weight;
- one AI evaluation JSON file per model.

The configured models currently include:

- Doximity Ask Instant;
- Doximity Ask Thinking;
- OpenEvidence Sackett / Regular;
- GPT-5.2.

### Model-letter mapping

The physician spreadsheet uses labels such as `Model_A`, `Model_B`, etc.

The script assigns these letters according to the **first appearance of each model in `cases_40.xlsx`**.

The order of models in `cases_40.xlsx` therefore matters. If that ordering changes without a corresponding change in the physician spreadsheet, the mapping can become incorrect.

### Physician spreadsheet structure

Rubric columns are identified from headers such as:

```text
Model_D__Case_1138_Rubric_1 — Accuracy — 8 points
```

Each nonempty row is treated as one physician judge. At least two physician rows are required.

### Score validation and binary conversion

Every rubric rating is expected to be either:

```text
0
```

or the rubric's signed point value.

Unexpected values cause the script to stop rather than silently recode the data.

The script then creates a binary `met` representation:

```text
score == 0  -> met = 0
score != 0  -> met = 1
```

Interpretation depends on the sign of the rubric criterion:

- positive criterion + `met = 1`: desired information/behavior was present;
- negative criterion + `met = 1`: undesirable or penalized behavior was present.

Thus, `met` means **the criterion was triggered**, not necessarily that the model behaved correctly.

### Agreement metric: HealthBench-style Macro F1

For each rater/reference comparison, the script creates a binary confusion matrix:

- TP: both raters say `met`;
- TN: both raters say `not met`;
- FP: evaluated rater says `met`, reference says `not met`;
- FN: evaluated rater says `not met`, reference says `met`.

It then calculates:

```text
F1_met      = F1 for the met class
F1_not_met  = F1 for the not-met class
Macro F1    = (F1_met + F1_not_met) / 2
```

Macro F1 gives equal importance to the two classes and is therefore less dominated by class prevalence than raw accuracy.

### Pairing strategy

No physician consensus or majority vote is created.

Instead:

- each physician is compared directly with every other physician;
- the AI judge is compared directly with each physician;
- physician-specific Macro F1 values are calculated;
- `physician_mean` is the arithmetic mean of the individual physician Macro F1 values.

This preserves physician disagreement rather than masking it through consensus voting.

### Outputs

Files are written to:

```text
outputs/analysis/
```

#### `01_physician_responses_original.xlsx`

An unchanged copy of the original physician-response workbook.

#### `02_scores_combined.xlsx`

Long-format dataset joining rubric definitions, AI scores, and physician scores.

Key columns include:

- `case_id`;
- `model`;
- `model_letter`;
- `rubric_item`;
- `criterion`;
- `axis`;
- `points`;
- `judge_gpt`;
- one column per physician judge.

#### `03_binary_met.xlsx`

Adds binary `*_met` columns for the AI judge and every physician while retaining the original weighted scores.

This is the most direct file for inspecting individual rubric disagreements.

#### `04_pairwise_comparisons.xlsx`

One row per pairwise rater/reference comparison at the rubric-item level.

Key fields include:

- case and rubric identifiers;
- model;
- axis;
- signed rubric weight;
- evaluated `rater`;
- `reference` judge;
- `pred_met`;
- `reference_met`.

#### `05_macro_f1.xlsx`

Primary agreement summary, reported overall (`axis = All`) and separately for each clinical axis.

For each rater, fields include:

- number of comparisons;
- TP, FP, FN, TN;
- F1 for `met`;
- F1 for `not met`;
- Macro F1.

A `physician_mean` row summarizes the average physician Macro F1 for each axis.

### Interpretation

The central comparison is:

```text
AI judge Macro F1 vs individual physicians
                    compared with
physician-physician Macro F1 / physician_mean
```

If AI-physician Macro F1 is close to the physician benchmark, this supports use of the AI judge as a reproducible rubric evaluator for this dataset. Macro F1 agreement, however, does not by itself establish clinical validity; it measures concordance with the physician ratings used in this study.

### Run

```bash
python evaluate/clinical_AI_judges.py
```

---

## Summary of Research Outputs

| Script | Primary question | Main outputs |
|---|---|---|
| `prepare.py` | Can raw evaluation runs be harmonized into case-, rubric-, axis-, and text-level analysis tables? | `case_scores.csv`, `rubric_judgments.csv`, `text_metrics.csv`, `axis_errors.csv` |
| `stability_axes.py` | Are scores and rubric decisions reproducible, do models differ, and where do axis-specific errors occur? | `score_summary.csv`, `case_score_stability.csv`, `model_comparison_friedman.csv`, `rubric_met_stability.csv`, `rubric_stability_by_axis.csv`, `axis_summary.csv`, `axis_error_stability.csv` |
| `references_length.py` | Are response length, references, and publication year associated with performance? | `length_reference_case_data.csv`, `reference_length_summary.csv`, `performance_correlations.csv` |
| `clinical_AI_judges.py` | How closely does the AI judge agree with physicians relative to physician-physician agreement? | `01_physician_responses_original.xlsx`, `02_scores_combined.xlsx`, `03_binary_met.xlsx`, `04_pairwise_comparisons.xlsx`, `05_macro_f1.xlsx` |

---

## Recommended Interpretation Order

For a manuscript or technical report:

1. **Overall performance:** summarize scores and confidence intervals from `score_summary.csv`.
2. **Model comparison:** report the matched-case Friedman test from `model_comparison_friedman.csv`.
3. **Judge reproducibility:** report case-level and rubric-level repeatability from `case_score_stability.csv` and `rubric_met_stability.csv`.
4. **Independent-run reproducibility:** report LB-vs-SJ comparisons from the same stability outputs.
5. **Clinical-axis analysis:** report axis-specific accuracy/error burden and reproducibility from `axis_summary.csv`, `rubric_stability_by_axis.csv`, and `axis_error_stability.csv`.
6. **Response characteristics:** report descriptive reference/length characteristics and correlations from `reference_length_summary.csv` and `performance_correlations.csv`.
7. **AI-judge validation:** compare AI-physician Macro F1 with physician-physician agreement using `05_macro_f1.xlsx`.

Multiple statistical tests are produced across models, users, axes, and predictors. If inferential claims are made across many tests, a multiple-comparison strategy should be specified in the analysis plan or manuscript.

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
      "points": 10,
      "axe": "Accuracy"
    },
    {
      "criterion": "Does the model incorrectly recommend antibiotics?",
      "points": -5,
      "axe": "Accuracy"
    }
  ]
}
```

- **Positive `points`** reward inclusion of expected clinical information.
- **Negative `points`** penalize specified undesirable content, hallucinations, contraindications, or safety risks.
- Rubric evaluation is binary at the item level; the corresponding weighted score is `0` or the signed rubric weight.
- Case-level metric calculations are performed by the metric scripts and then consumed by the research-analysis pipeline.

---

## License

This project is licensed under the [MIT License](LICENSE). See the `LICENSE` file for details.

The benchmark data is intended solely for **research evaluation**. It must not be treated as medical advice, used for self-diagnosis or treatment planning, or used for training clinical deployment models without regulatory validation.
