"""Normalize Freddie Mac STACR-style public CRT disclosure rows for C-DAG validation.

WARNING:
Public CRT loan-level validation only.
Not production validation, not consumer credit eligibility, and not regulatory compliance proof.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from public_mortgage_validation_common import first_value, normalize_header, to_float, to_int


CRT_NORMALIZED_COLUMNS: tuple[str, ...] = (
    "source_dataset",
    "source_record_id",
    "tenant_id",
    "leverage_risk",
    "borrower_credit_risk",
    "loan_performance_risk",
    "property_or_pool_segment",
    "delinquency_or_loss_proxy",
    "crt_escalation_risk",
    "segment",
    "mapping_notes",
)


def _detect_delimiter(header_line: str) -> str:
    return "|" if header_line.count("|") > header_line.count(",") else ","


def _load_text(path: Path, *, encoding: str, zip_member: str | None) -> str:
    if path.suffix.lower() != ".zip":
        return path.read_text(encoding=encoding)

    with zipfile.ZipFile(path, "r") as zf:
        member_name = zip_member
        if member_name is None:
            candidates = [
                info.filename
                for info in zf.infolist()
                if not info.is_dir() and info.filename.lower().endswith((".csv", ".txt"))
            ]
            if not candidates:
                raise ValueError("ZIP input contains no .csv or .txt members")
            member_name = candidates[0]
        with zf.open(member_name, "r") as fh:
            return fh.read().decode(encoding)


def _read_rows(
    *,
    input_path: Path,
    delimiter: str,
    encoding: str,
    zip_member: str | None,
) -> list[dict[str, str]]:
    text = _load_text(input_path, encoding=encoding, zip_member=zip_member)
    if not text.strip():
        raise ValueError(f"Input is empty: {input_path}")

    first_line = next((line for line in text.splitlines() if line.strip()), "")
    parsed_delimiter = _detect_delimiter(first_line) if delimiter == "auto" else delimiter

    reader = csv.DictReader(io.StringIO(text), delimiter=parsed_delimiter)
    if reader.fieldnames is None:
        raise ValueError(f"Input is missing a header row: {input_path}")

    headers = [normalize_header(name) for name in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {
            headers[idx]: str(value).strip()
            for idx, value in enumerate(raw.values())
            if idx < len(headers)
        }
        rows.append(row)
    return rows


def _is_adverse_outcome(row: dict[str, str]) -> bool:
    delinquency = first_value(
        row,
        (
            "current_loan_delinquency_status",
            "delinquency_status",
            "dq_status",
            "payment_status",
        ),
    )
    if delinquency:
        token = delinquency.strip().upper()
        if token in {"RA", "REO", "FC", "F", "D", "LOSS"}:
            return True
        parsed = to_int(token)
        if parsed is not None and parsed >= 3:
            return True

    days_delinquent = to_int(first_value(row, ("days_delinquent", "days_past_due", "current_days_delinquent")))
    if days_delinquent is not None and days_delinquent >= 60:
        return True

    realized_loss = to_float(first_value(row, ("cumulative_loss", "realized_loss", "net_loss", "loss_amount")))
    if realized_loss is not None and realized_loss > 0:
        return True
    return False


def _map_leverage_risk(row: dict[str, str]) -> str:
    leverage = to_float(
        first_value(
            row,
            (
                "current_cltv",
                "combined_ltv",
                "cltv",
                "current_ltv",
                "original_ltv",
                "ltv",
                "loan_to_value",
            ),
        )
    )
    if leverage is not None:
        return "high_leverage" if leverage >= 80 else "lower_leverage"
    return "high_leverage"


def _map_borrower_credit_risk(row: dict[str, str]) -> str:
    fico = to_int(first_value(row, ("credit_score", "borrower_credit_score", "fico", "original_fico")))
    if fico is not None:
        return "elevated_credit_risk" if fico < 680 else "lower_credit_risk"
    return "elevated_credit_risk"


def _map_segment_state(row: dict[str, str]) -> tuple[str, str]:
    segment_raw = first_value(
        row,
        (
            "deal_name",
            "pool_id",
            "pool_identifier",
            "pool_prefix",
            "property_state",
            "state",
            "msa",
        ),
    ) or "unspecified"
    return segment_raw, segment_raw.upper()


def _normalize_row(row: dict[str, str], index: int) -> dict[str, str]:
    leverage_risk = _map_leverage_risk(row)
    borrower_credit_risk = _map_borrower_credit_risk(row)
    adverse = _is_adverse_outcome(row)
    segment_value, segment_token = _map_segment_state(row)

    stressed_keywords = ("STACR", "SUB", "RISK", "IO", "NEG", "ALT", "NONOWNER", "NON_OWNER")
    stressed = any(keyword in segment_token for keyword in stressed_keywords)
    if leverage_risk == "high_leverage" and borrower_credit_risk == "elevated_credit_risk":
        stressed = True

    property_or_pool_segment = "stressed_segment" if stressed else "standard_segment"
    delinquency_or_loss_proxy = "adverse_proxy" if adverse else "benign_proxy"
    performance_high = adverse or (
        leverage_risk == "high_leverage" and borrower_credit_risk == "elevated_credit_risk"
    )
    loan_performance_risk = "high_performance_risk" if performance_high else "lower_performance_risk"
    escalation_high = adverse or (
        loan_performance_risk == "high_performance_risk"
        and property_or_pool_segment == "stressed_segment"
    )
    crt_escalation_risk = "high_escalation" if escalation_high else "low_escalation"

    source_record_id = (
        first_value(
            row,
            ("loan_sequence_number", "loan_id", "loan_identifier", "id"),
        )
        or f"stacr_{index}"
    )
    mapping_notes = (
        "leverage_from_ltv_cltv;"
        "borrower_credit_from_fico;"
        "performance_proxy_from_delinquency_loss_leverage;"
        "segment_proxy_from_deal_pool_property_fields;"
        "escalation_proxy_from_performance_and_segment"
    )

    return {
        "source_dataset": "freddie_mac_stacr_loan_level",
        "source_record_id": source_record_id,
        "tenant_id": "default",
        "leverage_risk": leverage_risk,
        "borrower_credit_risk": borrower_credit_risk,
        "loan_performance_risk": loan_performance_risk,
        "property_or_pool_segment": property_or_pool_segment,
        "delinquency_or_loss_proxy": delinquency_or_loss_proxy,
        "crt_escalation_risk": crt_escalation_risk,
        "segment": segment_value,
        "mapping_notes": mapping_notes,
    }


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CRT_NORMALIZED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CRT_NORMALIZED_COLUMNS})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Freddie STACR-style CRT validation input.")
    parser.add_argument("--input", required=True, help="Path to local STACR disclosure file (.csv/.txt/.zip).")
    parser.add_argument(
        "--output",
        default=str(ROOT / "validation" / "outputs" / "freddie_stacr_normalized.csv"),
        help="Normalized output CSV path.",
    )
    parser.add_argument(
        "--delimiter",
        default="auto",
        help="Input delimiter, or 'auto' to detect from header line.",
    )
    parser.add_argument("--encoding", default="utf-8-sig", help="Input text encoding.")
    parser.add_argument("--zip-member", default=None, help="Optional member name when --input points to a ZIP file.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional max rows to normalize.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_rows is not None and args.max_rows <= 0:
        raise ValueError("--max-rows must be a positive integer")

    rows = _read_rows(
        input_path=Path(args.input),
        delimiter=args.delimiter,
        encoding=args.encoding,
        zip_member=args.zip_member,
    )

    normalized: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        normalized.append(_normalize_row(row, idx))
        if args.max_rows is not None and len(normalized) >= args.max_rows:
            break

    _write_rows(Path(args.output), normalized)
    print(f"prepared_rows={len(normalized)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
