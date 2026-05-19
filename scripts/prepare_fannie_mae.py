"""Normalize Fannie Mae SF loan performance files into engine-compatible CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from public_mortgage_validation_common import (
    normalize_header,
    normalized_record,
    read_delimited_rows,
    write_normalized_csv,
)


FANNIE_ACQUISITION_FIELDS: list[str] = [
    "loan_identifier",
    "channel",
    "seller_name",
    "original_interest_rate",
    "original_upb",
    "original_loan_term",
    "origination_date",
    "first_payment_date",
    "original_ltv",
    "original_cltv",
    "number_of_borrowers",
    "debt_to_income_ratio",
    "borrower_credit_score",
    "first_time_home_buyer_indicator",
    "loan_purpose",
    "property_type",
    "number_of_units",
    "occupancy_status",
    "property_state",
    "zip_3_digit",
    "mortgage_insurance_percentage",
    "product_type",
    "co_borrower_credit_score",
]

FANNIE_PERFORMANCE_FIELDS: list[str] = [
    "loan_identifier",
    "monthly_reporting_period",
    "servicer_name",
    "current_interest_rate",
    "current_actual_upb",
    "loan_age",
    "remaining_months_to_legal_maturity",
    "adjusted_remaining_months_to_maturity",
    "maturity_date",
    "msa",
    "current_loan_delinquency_status",
    "modification_flag",
    "zero_balance_code",
]


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _build_performance_index(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        loan_id = row.get(normalize_header("loan_identifier"), "").strip()
        if not loan_id:
            continue
        current = indexed.get(loan_id)
        if current is None:
            indexed[loan_id] = row
            continue

        current_status = current.get("current_loan_delinquency_status", "").strip().upper()
        new_status = row.get("current_loan_delinquency_status", "").strip().upper()
        current_age = _to_int(current.get("loan_age", "0"))
        new_age = _to_int(row.get("loan_age", "0"))

        if new_status in {"RA", "REO", "FC", "F"} and current_status not in {"RA", "REO", "FC", "F"}:
            indexed[loan_id] = row
            continue
        if new_age > current_age:
            indexed[loan_id] = row
    return indexed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare Fannie Mae public institutional loan-level validation input."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to single-file Fannie historical performance file (pipe-delimited, headerless).",
    )
    parser.add_argument("--acquisition-input", default=None, help="Path to Fannie acquisition file")
    parser.add_argument("--performance-input", default=None, help="Optional Fannie performance file")
    parser.add_argument(
        "--output",
        default=str(ROOT / "validation" / "outputs" / "fannie_mae_normalized.50k.csv"),
        help="Normalized output CSV path",
    )
    parser.add_argument("--delimiter", default="|", help="Input delimiter")
    parser.add_argument("--encoding", default="utf-8-sig", help="Input encoding")
    parser.add_argument(
        "--has-header",
        action="store_true",
        help="Set if input files include a header row",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional maximum number of rows to normalize.",
    )
    return parser


def _coalesce(*values: str) -> str:
    for value in values:
        if str(value).strip() != "":
            return str(value).strip()
    return ""


def _normalize_single_file_row(raw_row: list[str], row_idx: int) -> dict[str, str]:
    row = [value.strip() for value in raw_row]
    if len(row) == 112:
        row = ["", *row]
    if len(row) == 114 and row[-1] == "":
        row = row[:-1]
    if len(row) < 113:
        raise ValueError(
            f"Row {row_idx} has {len(row)} columns; expected at least 113 for Fannie historical performance format."
        )

    loan_id = row[1].strip() or f"fannie_{row_idx}"
    mapped = {
        "loan_identifier": loan_id,
        "monthly_reporting_period": row[2].strip(),
        "current_actual_upb": _coalesce(row[9], row[11]),
        "original_loan_term": row[12].strip(),
        "origination_date": row[13].strip(),
        "first_payment_date": row[14].strip(),
        "loan_age": row[15].strip(),
        "remaining_months_to_legal_maturity": row[16].strip(),
        "maturity_date": row[18].strip(),
        "original_loan_to_value": row[19].strip(),
        "original_combined_loan_to_value": row[20].strip(),
        "number_of_borrowers": row[21].strip(),
        "original_debt_to_income_ratio": row[22].strip(),
        "borrower_credit_score": row[23].strip(),
        "co_borrower_credit_score": row[24].strip(),
        "first_time_home_buyer_indicator": row[25].strip(),
        "occupancy_status": row[27].strip(),
        "number_of_units": row[28].strip(),
        "channel": row[29].strip(),
        "property_state": row[30].strip(),
        "msa": row[31].strip(),
        "zip_3_digit": row[32].strip(),
        "mortgage_insurance_percentage": row[33].strip(),
        "product_type": row[34].strip(),
        # Delinquency status is required for risk proxy mapping.
        "current_loan_delinquency_status": row[39].strip(),
        "zero_balance_code": row[43].strip() if len(row) > 43 else "",
    }
    return normalized_record(
        source_dataset="fannie_mae_sf_performance",
        source_record_id=loan_id,
        row=mapped,
    )


def main() -> int:
    args = build_parser().parse_args()
    if args.input:
        normalized_rows: list[dict[str, str]] = []
        input_path = Path(args.input)
        with input_path.open("r", encoding=args.encoding, newline="") as fh:
            reader = csv.reader(fh, delimiter=args.delimiter)
            for idx, raw_row in enumerate(reader, start=1):
                if not raw_row or not "".join(raw_row).strip():
                    continue
                normalized_rows.append(_normalize_single_file_row(raw_row, idx))
                if args.max_rows is not None and len(normalized_rows) >= args.max_rows:
                    break

        write_normalized_csv(args.output, normalized_rows)
        print(f"prepared_rows={len(normalized_rows)} output={args.output}")
        return 0

    if not args.acquisition_input:
        raise ValueError(
            "Either --input (single-file historical performance) or --acquisition-input must be provided."
        )

    acq_rows = read_delimited_rows(
        input_path=args.acquisition_input,
        delimiter=args.delimiter,
        has_header=args.has_header,
        fieldnames=None if args.has_header else FANNIE_ACQUISITION_FIELDS,
        encoding=args.encoding,
    )

    performance_by_loan: dict[str, dict[str, str]] = {}
    if args.performance_input:
        perf_rows = read_delimited_rows(
            input_path=args.performance_input,
            delimiter=args.delimiter,
            has_header=args.has_header,
            fieldnames=None if args.has_header else FANNIE_PERFORMANCE_FIELDS,
            encoding=args.encoding,
        )
        performance_by_loan = _build_performance_index(perf_rows)

    normalized_rows: list[dict[str, str]] = []
    for idx, acq in enumerate(acq_rows, start=1):
        if args.max_rows is not None and idx > args.max_rows:
            break
        loan_id = acq.get(normalize_header("loan_identifier"), "").strip() or f"fannie_{idx}"
        merged = dict(acq)
        if loan_id in performance_by_loan:
            merged.update(performance_by_loan[loan_id])
        normalized_rows.append(
            normalized_record(
                source_dataset="fannie_mae_sf_performance",
                source_record_id=loan_id,
                row=merged,
            )
        )

    write_normalized_csv(args.output, normalized_rows)
    print(f"prepared_rows={len(normalized_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
