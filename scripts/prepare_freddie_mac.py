"""Normalize Freddie Mac SF loan-level files into engine-compatible CSV."""

from __future__ import annotations

import argparse
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


FREDDIE_ORIGINATION_FIELDS: list[str] = [
    "credit_score",
    "first_payment_date",
    "first_time_homebuyer_flag",
    "maturity_date",
    "msa",
    "mortgage_insurance_percentage",
    "number_of_units",
    "occupancy_status",
    "original_combined_loan_to_value",
    "original_debt_to_income_ratio",
    "original_upb",
    "original_loan_to_value",
    "original_interest_rate",
    "channel",
    "prepayment_penalty_mortgage_flag",
    "product_type",
    "property_state",
    "property_type",
    "postal_code",
    "loan_sequence_number",
    "loan_purpose",
    "original_loan_term",
    "number_of_borrowers",
    "seller_name",
    "servicer_name",
    "super_conforming_flag",
]

FREDDIE_PERFORMANCE_FIELDS: list[str] = [
    "loan_sequence_number",
    "monthly_reporting_period",
    "current_actual_upb",
    "current_loan_delinquency_status",
    "loan_age",
    "remaining_months_to_legal_maturity",
    "repurchase_flag",
    "modification_flag",
    "zero_balance_code",
    "zero_balance_effective_date",
    "current_interest_rate",
    "current_deferred_upb",
    "due_date_of_last_paid_installment",
]

FREDDIE_LLD_90_FIELDS: list[str] = [f"col_{idx:02d}" for idx in range(1, 91)]
FREDDIE_LLD_90_FIELDS[0] = "monthly_reporting_period"
FREDDIE_LLD_90_FIELDS[1] = "dataset_id"
FREDDIE_LLD_90_FIELDS[2] = "loan_sequence_number"
FREDDIE_LLD_90_FIELDS[5] = "property_state"
FREDDIE_LLD_90_FIELDS[16] = "loan_purpose"
FREDDIE_LLD_90_FIELDS[22] = "credit_score"
FREDDIE_LLD_90_FIELDS[23] = "original_loan_to_value"
FREDDIE_LLD_90_FIELDS[24] = "original_combined_loan_to_value"
FREDDIE_LLD_90_FIELDS[25] = "original_debt_to_income_ratio"
FREDDIE_LLD_90_FIELDS[33] = "loan_age"
FREDDIE_LLD_90_FIELDS[36] = "current_loan_delinquency_status"
FREDDIE_LLD_90_FIELDS[42] = "zero_balance_code"
FREDDIE_LLD_90_FIELDS[43] = "zero_balance_effective_date"


def _infer_fieldnames(
    *,
    input_path: str,
    has_header: bool,
    delimiter: str,
    encoding: str,
    default_fields: list[str],
) -> list[str] | None:
    if has_header:
        return None

    with Path(input_path).open("r", encoding=encoding) as fh:
        first_line = fh.readline().rstrip("\n")
    field_count = len(first_line.split(delimiter))
    if field_count == 90:
        return FREDDIE_LLD_90_FIELDS
    if field_count == 4:
        raise ValueError(
            "Freddie summary/control files are not supported as origination/performance input. "
            "Use a 90-column loan-level *_lld.txt file."
        )
    return default_fields


def _build_performance_index(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    def _to_int(value: str) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        loan_id = row.get(normalize_header("loan_sequence_number"), "").strip()
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
        description="Prepare Freddie Mac public institutional loan-level validation input."
    )
    parser.add_argument("--origination-input", required=True, help="Path to Freddie origination file")
    parser.add_argument("--performance-input", default=None, help="Optional Freddie monthly performance file")
    parser.add_argument(
        "--output",
        default=str(ROOT / "validation" / "outputs" / "freddie_mac_normalized.csv"),
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
        help="Optional maximum number of origination rows to normalize.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    origination_fields = _infer_fieldnames(
        input_path=args.origination_input,
        has_header=args.has_header,
        delimiter=args.delimiter,
        encoding=args.encoding,
        default_fields=FREDDIE_ORIGINATION_FIELDS,
    )
    orig_rows = read_delimited_rows(
        input_path=args.origination_input,
        delimiter=args.delimiter,
        has_header=args.has_header,
        fieldnames=origination_fields,
        encoding=args.encoding,
    )

    performance_by_loan: dict[str, dict[str, str]] = {}
    if args.performance_input:
        performance_fields = _infer_fieldnames(
            input_path=args.performance_input,
            has_header=args.has_header,
            delimiter=args.delimiter,
            encoding=args.encoding,
            default_fields=FREDDIE_PERFORMANCE_FIELDS,
        )
        perf_rows = read_delimited_rows(
            input_path=args.performance_input,
            delimiter=args.delimiter,
            has_header=args.has_header,
            fieldnames=performance_fields,
            encoding=args.encoding,
        )
        performance_by_loan = _build_performance_index(perf_rows)

    normalized_rows: list[dict[str, str]] = []
    for idx, orig in enumerate(orig_rows, start=1):
        if args.max_rows is not None and idx > args.max_rows:
            break
        loan_id = orig.get(normalize_header("loan_sequence_number"), "").strip() or f"freddie_{idx}"
        merged = dict(orig)
        if loan_id in performance_by_loan:
            merged.update(performance_by_loan[loan_id])
        normalized_rows.append(
            normalized_record(
                source_dataset="freddie_mac_sf_loan_level",
                source_record_id=loan_id,
                row=merged,
            )
        )

    write_normalized_csv(args.output, normalized_rows)
    print(f"prepared_rows={len(normalized_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
