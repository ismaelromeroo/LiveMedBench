#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STAGE 2 — JSON conversion.

Converts the exported Form_Responses rows (CSV) into the per-model input files
that the LiveMedBench evaluation pipeline consumes, by joining each submitted
response against the case metadata in Subset_LiveMedBench_v202604_new.json
(produced by STAGE 1, pipeline/prepare_subset.py).

Primary output — one file per model, matching input_OE_2026-08-10.json:

    outputs/input_<MODEL>_<DATE>.json
        [{"case_id", "post_time", "narrative", "core_request",
          "model_response", "finish_reason", "doctor_advice"}, ...]

    One file PER MODEL, so that OE and Doximity case_ids are never mixed in a
    single file (evaluate_model.py keys on case_id alone, so mixing models
    causes collisions). Duplicate submissions of the same case_id for the same
    model are reduced to the first submission, for the same reason.

Secondary outputs — unchanged from the original script, retained for review:

    outputs/model_results_<model>.json    raw response text per case
    outputs/analysis_summary.json         word / reference / year metrics
    outputs/readable_reports.txt          plain-language physician summaries

How to get the input CSV:
    In Google Sheets: File > Download > Comma Separated Values (.csv)

Usage:
    python3 pipeline/sheet_to_json.py \
        --input-csv data/Form_Responses.csv \
        --subset-file data/Subset_LiveMedBench_v202604_new.json \
        --output-dir outputs/ \
        --run-date 2026-08-10
"""

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Column mapping (adjustable in case the Form/Sheet headers ever change)
# ---------------------------------------------------------------------------

COLUMN_MAP = {
    "timestamp": "Timestamp",
    "model": "Model",
    "case_id": "Case number",
    "execution_time": "Execution time",
    "model_response": "Paste in all model output.",
    "source_url": "Paste in the URL related this query",
}


# ---------------------------------------------------------------------------
# Text analysis (heading detection extended to cover References, Sources,
# Bibliography, Works Cited, Literature — per Vanessa's 7/20 email and
# verified against OpenEvidence + Doximity real cases)
# ---------------------------------------------------------------------------

def split_main_text_and_references(text: str) -> tuple[str, str]:
    heading_pattern = re.compile(
        r"(?im)"
        r"^\s{0,3}"
        r"(?:#{1,6}\s*)?"
        r"(?:\*{0,2})"
        r"(?:references|bibliography|works cited|sources|literature)"
        r"(?:\*{0,2})"
        r"\s*:?\s*$"
    )
    match = heading_pattern.search(text)
    if match is None:
        return text, ""
    return text[:match.start()], text[match.end():]


def remove_trailing_source_blocks(main_text: str) -> tuple[str, bool]:
    lines = main_text.splitlines()
    for index, line in enumerate(lines):
        is_figure_or_table_heading = re.fullmatch(
            r"\s*(?:Figure|Table)\s+\d+\s*", line, flags=re.IGNORECASE
        )
        if not is_figure_or_table_heading:
            continue
        remaining_text = "\n".join(lines[index:])
        contains_source_information = bool(
            re.search(
                r"(?:\bdoi\s*:\s*10\.|\bJournal\b|\bJAMA\b|\bCirculation\b"
                r"|\bClinical Endocrinology\b|\bNew England Journal\b"
                r"|\bAmerican Family Physician\b)",
                remaining_text, flags=re.IGNORECASE
            )
        )
        if contains_source_information:
            return "\n".join(lines[:index]).rstrip(), True
    return main_text.rstrip(), False


def remove_numerical_citations(text: str) -> str:
    pattern = re.compile(
        r"\[\s*\d+(?:\s*[-–—]\s*\d+)?(?:\s*,\s*\d+(?:\s*[-–—]\s*\d+)?)*\s*\]"
    )
    return pattern.sub(" ", text)


def remove_parenthetical_author_year_citations(text: str) -> str:
    surname = r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*"
    author_expression = (
        surname + r"(?:\s+et\s+al\.?|\s+(?:and|&)\s+" + surname
        + r"|\s+" + surname + r")*"
    )
    single_citation = author_expression + r"\s*,?\s*(?:19|20)\d{2}[a-z]?"
    pattern = re.compile(
        r"\(\s*" + single_citation + r"(?:\s*;\s*" + single_citation
        + r")*\s*\)", flags=re.IGNORECASE
    )
    return pattern.sub(" ", text)


def remove_narrative_author_year_citations(text: str) -> str:
    surname = r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*"
    pattern = re.compile(
        r"\b" + surname + r"(?:\s+et\s+al\.?|\s+(?:and|&)\s+" + surname
        + r"|\s+" + surname + r")*\s*\(\s*(?:19|20)\d{2}[a-z]?\s*\)"
    )
    return pattern.sub(" ", text)


def remove_in_text_citations(text: str) -> str:
    text = remove_numerical_citations(text)
    text = remove_parenthetical_author_year_citations(text)
    text = remove_narrative_author_year_citations(text)
    return text


def extract_valid_words(text: str) -> list[str]:
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"(?m)^\s*[-+•]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+\.\s+", "", text)
    raw_tokens = re.split(r"\s+", text.strip())
    valid_words = []
    for token in raw_tokens:
        if not token:
            continue
        cleaned_token = re.sub(
            r"^[^\wÀ-ÖØ-öø-ÿ%≥≤~]+|[^\wÀ-ÖØ-öø-ÿ%≥≤~]+$", "", token
        )
        if cleaned_token and any(c.isalnum() for c in cleaned_token):
            valid_words.append(cleaned_token)
    return valid_words


def parse_numbered_references(reference_text: str) -> list[tuple[int, str]]:
    entry_starts = list(re.finditer(r"(?m)^\s*(\d+)\.\s+", reference_text))
    entries = []
    for index, match in enumerate(entry_starts):
        reference_number = int(match.group(1))
        content_start = match.end()
        content_end = (
            entry_starts[index + 1].start()
            if index + 1 < len(entry_starts)
            else len(reference_text)
        )
        reference = re.sub(
            r"\s+", " ", reference_text[content_start:content_end]
        ).strip()
        entries.append((reference_number, reference))
    return entries


def normalize_reference(reference: str) -> str:
    normalized = reference.casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def remove_duplicate_references(
    entries: list[tuple[int, str]]
) -> list[tuple[int, str]]:
    seen: dict[str, int] = {}
    distinct = []
    for reference_number, reference in entries:
        key = normalize_reference(reference)
        if key in seen:
            continue
        seen[key] = reference_number
        distinct.append((reference_number, reference))
    return distinct


def extract_publication_year(reference: str) -> Optional[int]:
    reference_without_identifiers = re.sub(
        r"(?:doi\s*:\s*\S+|https?://\S+|www\.\S+)", " ", reference,
        flags=re.IGNORECASE
    )
    journal_years = re.findall(
        r"\b((?:19|20)\d{2})\s*;", reference_without_identifiers
    )
    if journal_years:
        return int(journal_years[-1])
    comma_years = re.findall(
        r",\s*((?:19|20)\d{2})\b", reference_without_identifiers
    )
    if comma_years:
        return int(comma_years[-1])
    possible_years = re.findall(
        r"\b((?:19|20)\d{2})\b", reference_without_identifiers
    )
    if possible_years:
        return int(possible_years[-1])
    return None


def check_source_domain_contamination(reference_text: str, source_url: str = "") -> dict:
    """
    Simple substring check (not an LLM task) confirming no reference cites
    the original case-source domains (iCliniq.com or studentdoctor.net).
    Flags possible retrieval/training contamination per Bob Hoyt's request.
    """
    combined = f"{reference_text}\n{source_url}".lower()
    flagged_domains = [
        domain for domain in ("icliniq.com", "studentdoctor.net")
        if domain in combined
    ]
    return {
        "contains_source_domain": bool(flagged_domains),
        "flagged_domains": flagged_domains,
    }


def analyze_document(text: str, source_url: str = "") -> dict:
    """
    Returns, per Vanessa's spec (7/23 email):
      1. main_text_word_count      - word count of main chunk
      2. total_reference_count     - number of references found
      3. reference_years           - list of {reference_number, year}, where
                                      year is an int OR the string "NOTFOUND"
      4. average_publication_year  - average of only the valid (int) years
      5. references_found_heading  - whether a References/Sources/etc.
                                      heading was located at all

    Also includes a simple substring-based contamination check (Bob's
    7/23 request) confirming no reference cites icliniq.com or
    studentdoctor.net, the original case-source domains.
    """
    main_text, reference_text = split_main_text_and_references(text)
    main_text, _ = remove_trailing_source_blocks(main_text)
    citation_free_main_text = remove_in_text_citations(main_text)
    valid_words = extract_valid_words(citation_free_main_text)

    parsed_references = parse_numbered_references(reference_text)
    distinct_references = remove_duplicate_references(parsed_references)

    reference_years = []
    for reference_number, reference in distinct_references:
        year = extract_publication_year(reference)
        reference_years.append({
            "reference_number": reference_number,
            "year": year if isinstance(year, int) else "NOTFOUND",
        })

    valid_years = [
        entry["year"] for entry in reference_years
        if isinstance(entry["year"], int)
    ]
    average_publication_year = (
        round(sum(valid_years) / len(valid_years), 2)
        if valid_years else None
    )

    contamination = check_source_domain_contamination(
        reference_text, source_url
    )

    return {
        "main_text": citation_free_main_text,
        "main_text_word_count": len(valid_words),
        "total_reference_count": len(distinct_references),
        "reference_years": reference_years,
        "average_publication_year": average_publication_year,
        "references_found_heading": bool(reference_text),
        "contains_source_domain": contamination["contains_source_domain"],
        "flagged_domains": contamination["flagged_domains"],
    }


def format_readable_report(case_id: str, model: str, metrics: dict) -> str:
    """
    Build a plain-language summary of one case's analysis, meant to be read
    directly by a physician reviewer (no JSON literacy required).
    """
    lines = []
    lines.append(f"Case {case_id} — {model}")
    lines.append("-" * (len(f"Case {case_id} — {model}")))
    lines.append(f"Word count (main text):      {metrics['main_text_word_count']}")
    lines.append(f"References found:            {metrics['total_reference_count']}")

    if metrics["average_publication_year"] is not None:
        lines.append(f"Average reference year:      {metrics['average_publication_year']}")
    else:
        lines.append("Average reference year:      N/A (no valid years found)")

    notfound = [
        entry["reference_number"] for entry in metrics["reference_years"]
        if entry["year"] == "NOTFOUND"
    ]
    if notfound:
        lines.append(
            f"Years not found for refs:    {', '.join(str(n) for n in notfound)}"
        )

    if not metrics["references_found_heading"]:
        lines.append(
            "Note: No references heading was detected in this response "
            "(the response may not have included citations)."
        )

    if metrics["contains_source_domain"]:
        lines.append(
            f"CONTAMINATION FLAG: reference(s) cite {', '.join(metrics['flagged_domains'])} "
            "— the original case-source site. Review this case."
        )
    else:
        lines.append("Contamination check:         clear (no icliniq.com / studentdoctor.net citations)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sheet -> JSON conversion
# ---------------------------------------------------------------------------

def load_rows(input_csv: Path) -> list[dict]:
    with input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_subset_cases(subset_file: Path) -> dict[str, dict]:
    """
    Load Subset_LiveMedBench_v202604_new.json (STAGE 1 output) and key it by
    case_id as a string, so it can be joined against the Case number column
    from the Form export.
    """
    with subset_file.open("r", encoding="utf-8") as f:
        cases = json.load(f)
    return {str(case["case_id"]): case for case in cases}


def normalize_post_time(post_time) -> str:
    """
    The dataset stores post_time as a full timestamp ("2026-01-17T00:00:00"),
    while input_OE_2026-08-10.json carries the date only ("2026-01-17").
    Truncate at the "T" so the emitted files match that reference format.
    """
    if not isinstance(post_time, str):
        return post_time
    return post_time.split("T")[0]


def build_input_record(case: dict, cleaned_response: str) -> dict:
    """
    Assemble one record in the exact field order used by
    input_OE_2026-08-10.json.

    model_response carries the cleaned main text (references stripped, in-text
    citations removed, trailing table/figure source blocks dropped) rather than
    the raw pasted output — this matches how the reference input files were
    built and is what the evaluation pipeline expects.
    """
    return {
        "case_id": case["case_id"],
        "post_time": normalize_post_time(case.get("post_time", "")),
        "narrative": case.get("narrative", ""),
        "core_request": case.get("core_request", ""),
        "model_response": cleaned_response,
        "finish_reason": "stop",
        "doctor_advice": case.get("doctor_advice", ""),
    }


def convert(
    input_csv: Path,
    subset_file: Path,
    output_dir: Path,
    run_date: str,
) -> None:
    rows = load_rows(input_csv)
    print(f"Loaded {len(rows)} rows from {input_csv}")

    subset_cases = load_subset_cases(subset_file)
    print(f"Loaded {len(subset_cases)} cases from {subset_file}")

    by_model: dict[str, list[dict]] = {}
    input_records: dict[str, list[dict]] = {}
    seen_case_ids: dict[str, set[str]] = {}

    analysis_summary: list[dict] = []
    readable_reports: list[str] = []

    skipped = 0
    not_in_subset: list[tuple[str, str]] = []
    duplicates: list[tuple[str, str]] = []

    for row in rows:
        model = (row.get(COLUMN_MAP["model"]) or "").strip()
        case_id = (row.get(COLUMN_MAP["case_id"]) or "").strip()
        model_response = row.get(COLUMN_MAP["model_response"]) or ""
        source_url = row.get(COLUMN_MAP["source_url"]) or ""

        if not model or not case_id or not model_response.strip():
            skipped += 1
            continue

        # Build the run_model.py-compatible record.
        by_model.setdefault(model, []).append({
            "case_id": case_id,
            "model_response": model_response,
        })

        # Run word/reference/year analysis for review.
        metrics = analyze_document(model_response, source_url)
        analysis_summary.append({
            "case_id": case_id,
            "model": model,
            **metrics,
        })
        readable_reports.append(
            format_readable_report(case_id, model, metrics)
        )

        # ---- Join against the STAGE 1 subset to build the evaluation input ----
        case = subset_cases.get(case_id)
        if case is None:
            not_in_subset.append((model, case_id))
            continue

        # One entry per case_id per model: evaluate_model.py keys on case_id
        # alone, so a repeated submission would silently overwrite.
        already_seen = seen_case_ids.setdefault(model, set())
        if case_id in already_seen:
            duplicates.append((model, case_id))
            continue
        already_seen.add(case_id)

        input_records.setdefault(model, []).append(
            build_input_record(case, metrics["main_text"])
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Primary output: one evaluation input file per model ----
    for model, records in input_records.items():
        safe_model_name = re.sub(r"[^\w-]+", "_", model.strip())
        out_path = output_dir / f"input_{safe_model_name}_{run_date}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"  {model}: {len(records)} cases -> {out_path}")

    # ---- Secondary outputs, retained for review ----
    for model, records in by_model.items():
        safe_model_name = re.sub(r"[^\w-]+", "_", model.strip())
        out_path = output_dir / f"model_results_{safe_model_name}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    summary_path = output_dir / "analysis_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(analysis_summary, f, ensure_ascii=False, indent=2)

    readable_path = output_dir / "readable_reports.txt"
    with readable_path.open("w", encoding="utf-8") as f:
        f.write("\n\n".join(readable_reports))

    print(f"\nAnalysis summary ({len(analysis_summary)} rows) -> {summary_path}")
    print(f"Readable reports (for physician review) -> {readable_path}")

    if skipped:
        print(f"Skipped {skipped} row(s) missing model, case number, or response text.")
    if duplicates:
        print(f"\nDuplicate submissions reduced to first entry ({len(duplicates)}):")
        for model, case_id in duplicates:
            print(f"  {model} case {case_id}")
    if not_in_subset:
        print(f"\nSubmitted cases not present in the subset file ({len(not_in_subset)}):")
        for model, case_id in not_in_subset:
            print(f"  {model} case {case_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Form_Responses CSV export into LiveMedBench-format JSON."
    )
    parser.add_argument("--input-csv", type=str, required=True)
    parser.add_argument(
        "--subset-file", type=str, required=True,
        help="STAGE 1 output, e.g. data/Subset_LiveMedBench_v202604_new.json",
    )
    parser.add_argument("--output-dir", type=str, default="outputs")
    parser.add_argument(
        "--run-date", type=str, required=True,
        help="Date stamp for the emitted input files, e.g. 2026-08-10",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    convert(
        Path(args.input_csv),
        Path(args.subset_file),
        Path(args.output_dir),
        args.run_date,
    )


if __name__ == "__main__":
    main()