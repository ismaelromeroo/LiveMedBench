# Evaluation pipeline

Fork of [LiveMedBench](https://github.com/ZhilingYan/LiveMedBench), with a
pipeline wrapped around the upstream evaluation scripts so a run can be
reproduced end to end from the Google Form export.

Upstream scripts (`evaluate/evaluate_model.py`, `evaluate/metric_calc.py`) are
unmodified. `evaluate/metric_calc_by_ax_caseid.py` is included as provided.

Data and outputs are excluded from version control — see `.gitignore`.

---

## Layout

```
data/                                  (gitignored)
  LiveMedBench_v202604_new.json        full dataset, from Hugging Face
  cases-to-consider.xlsx               the 100 selected case_ids
  Form_Responses.csv                   Google Sheet export
  Subset_LiveMedBench_v202604_new.json STAGE 1 output

pipeline/
  prepare_subset.py                    STAGE 1
  sheet_to_json.py                     STAGE 2

evaluate/
  evaluate_model.py                    STAGE 3 (upstream, unmodified)
  metric_calc.py                       STAGE 4 (upstream, unmodified)
  metric_calc_by_ax_caseid.py          STAGE 5 (as provided)

outputs/                               (gitignored)
```

---

## Inputs to fetch before running

1. **Dataset** — `LiveMedBench_v202604_new.json` from
   <https://huggingface.co/datasets/JuelieYann/LiveMedBench/tree/main> → `data/`
2. **Case list** — `cases-to-consider.xlsx` → `data/`
3. **Responses** — the Google Sheet, File → Download → CSV → `data/Form_Responses.csv`

---

## STAGE 1 — Subset preparation

Filters the full dataset down to the case_ids listed in `cases-to-consider.xlsx`.

```bash
python3 pipeline/prepare_subset.py \
    --cases-file data/cases-to-consider.xlsx \
    --input-file data/LiveMedBench_v202604_new.json \
    --output-file data/Subset_LiveMedBench_v202604_new.json
```

Direct port of `Select Cases of Interest.ipynb`. The filtering operations are
reproduced exactly as written; nothing added, removed, or reordered.

Expected: `Saved 100 cases to data/Subset_LiveMedBench_v202604_new.json`

---

## STAGE 2 — JSON conversion

Joins each submitted response to its case metadata from STAGE 1 and emits one
evaluation input file per model.

```bash
python3 pipeline/sheet_to_json.py \
    --input-csv data/Form_Responses.csv \
    --subset-file data/Subset_LiveMedBench_v202604_new.json \
    --output-dir outputs/ \
    --run-date 2026-08-10
```

Output records carry the seven fields of `input_OE_2026-08-10.json`, in order:
`case_id`, `post_time`, `narrative`, `core_request`, `model_response`,
`finish_reason`, `doctor_advice`.

Three behaviours worth noting:

- **One file per model.** `evaluate_model.py` keys on `case_id` alone, so OE and
  Doximity responses in a single file collide. They are written separately.
- **Duplicates reduced to the first submission**, for the same reason. Any that
  are dropped are printed at the end of the run.
- **`model_response` is the cleaned main text** — references stripped, in-text
  citations removed, trailing table/figure source blocks dropped — matching how
  the reference input files were built.

Cases submitted through the Form that are not in the subset file are skipped and
listed at the end of the run.

---

## STAGE 3 — Evaluation

```bash
python3 evaluate/evaluate_model.py \
    --rubric-file data/Subset_LiveMedBench_v202604_new.json \
    --model-result-file outputs/input_OpenEvidence_2026-08-10.json \
    --output-file outputs/evaluation_results_OE_2026-08-10.json \
    --response-field model_response
```

Once per model. `--resume` is optional.

---

## STAGE 4 — Metrics

```bash
python3 evaluate/metric_calc.py \
    --rubric-file data/Subset_LiveMedBench_v202604_new.json \
    --evaluation-dir outputs \
    --output-file outputs/metric_results.txt
```

---

## STAGE 5 — Metrics per evaluation axis

`metric_calc.py` does not break results down by axis. This script does, per
Appendix D.1.2 of the paper.

```bash
python3 evaluate/metric_calc_by_ax_caseid.py \
    --rubric-file data/Subset_LiveMedBench_v202604_new.json \
    --evaluation-dir outputs \
    --output-file outputs/metric_results_by_axis_per_case.csv
```

Error rate per axis: for positive criteria a failure to satisfy is an error, for
negative criteria triggering the criterion is an error. 0 is the desideratum.
Blank means the axis was not present for that case.

---

## Validation status

**STAGE 1** reproduces the notebook: 100 cases, matching its printed output.

**STAGE 2** was checked field by field against `input_OE_2026-08-10.json`. Of the
19 cases in that reference file, 2 (834 and 1417) are in the current 100-case
subset, so those are the two that can be compared:

| case | result |
| :-- | :-- |
| 834 | all 7 fields identical, field order identical |
| 1417 | 6 of 7 identical; `doctor_advice` differs by 4 characters |

The 1417 difference is an encoding artefact, not a logic difference: the
reference file carries `â€“` where the dataset has an en-dash `–` (UTF-8 read as
CP1252). Verified by re-encoding — the reference text round-trips exactly to
ours. The pipeline output is the correct one.

**STAGES 3–5** are unmodified upstream scripts and have not been re-run here.

### Note on subset coverage

The 19 cases in the pilot run and the 100 in `cases-to-consider.xlsx` overlap on
2 cases only. Running STAGE 2 against the current Form export therefore yields 2
OE cases and 1 Doximity case rather than the pilot's 19 — the remaining 17 pilot
cases are not in the subset. This is expected if the 100-case list is the
forward-looking study set and the pilot was drawn separately, and it is the
reason the field-level comparison above covers 2 cases rather than 19.
