"""Run Public CRT loan-level validation workflow for C-DAG.

WARNING:
Public CRT loan-level validation only.
Not production validation, not consumer credit eligibility, and not regulatory compliance proof.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from causal_credit_risk.audit_chain import verify_audit_chain
from causal_credit_risk.batch import run_batch_csv
from causal_credit_risk.cli import run_decision
from causal_credit_risk.cpd_estimation import build_draft_model_config
from causal_credit_risk.fairness import compute_fairness_report
from causal_credit_risk.replay import replay_from_audit_payload
from export_evidence_pack import export_evidence_pack


REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_dataset",
    "source_record_id",
    "leverage_risk",
    "borrower_credit_risk",
    "loan_performance_risk",
    "property_or_pool_segment",
    "delinquency_or_loss_proxy",
    "crt_escalation_risk",
    "segment",
)

ALLOWED_STATES: dict[str, set[str]] = {
    "leverage_risk": {"high_leverage", "lower_leverage"},
    "borrower_credit_risk": {"elevated_credit_risk", "lower_credit_risk"},
    "loan_performance_risk": {"high_performance_risk", "lower_performance_risk"},
    "property_or_pool_segment": {"stressed_segment", "standard_segment"},
    "delinquency_or_loss_proxy": {"adverse_proxy", "benign_proxy"},
    "crt_escalation_risk": {"high_escalation", "low_escalation"},
}

DEFAULT_COUNTERFACTUALS: list[dict[str, str]] = [
    {"leverage_risk": "lower_leverage"},
    {"borrower_credit_risk": "lower_credit_risk"},
    {
        "leverage_risk": "lower_leverage",
        "borrower_credit_risk": "lower_credit_risk",
        "property_or_pool_segment": "standard_segment",
    },
]

DATASET_SOURCE_URLS: dict[str, str] = {
    "fannie_mae_cas_loan_level": "https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/cas-deal-performance",
    "freddie_mac_stacr_loan_level": "https://crt.freddiemac.com/stacr",
}


def _progress(message: str) -> None:
    print(f"[progress] {message}", file=sys.stderr, flush=True)


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"Missing header row in input: {path}")
        return [dict(row) for row in reader]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _validate_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    valid_rows: list[dict[str, str]] = []
    rejected_rows = 0
    for row in rows:
        missing = [col for col in REQUIRED_COLUMNS if not str(row.get(col, "")).strip()]
        if missing:
            rejected_rows += 1
            continue

        bad_state = False
        for col, allowed in ALLOWED_STATES.items():
            if str(row.get(col, "")).strip() not in allowed:
                bad_state = True
                break
        if bad_state:
            rejected_rows += 1
            continue

        valid_rows.append(row)
    return valid_rows, rejected_rows


def _decision_distribution(batch_rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {"APPROVE": 0, "REVIEW": 0, "DECLINE": 0, "error": 0}
    for row in batch_rows:
        if row.get("status") != "ok":
            counts["error"] += 1
            continue
        decision = row.get("decision", "")
        if decision in counts:
            counts[decision] += 1
        else:
            counts[decision] = 1
    return counts


def _write_report(
    *,
    report_path: Path,
    datasets_used: list[str],
    source_urls: list[str],
    rows_processed: int,
    accepted_rows: int,
    rejected_rows: int,
    decision_distribution: dict[str, int],
    replay_success_rate: float,
    audit_chain_valid: bool | None,
    evidence_pack_mode: str,
    evidence_pack_rows: int | None,
    mapped_fields: list[str],
    fairness_summary: dict[str, Any],
) -> None:
    lines = [
        "# Public CRT Loan-Level Validation Report",
        "",
        f"Generated: {_utc_now()}",
        "",
        "## Non-production disclaimer",
        "",
        "Public CRT loan-level validation. Not production validation, not consumer credit eligibility, and not regulatory compliance proof.",
        "",
        "## Dataset source",
        "",
        ", ".join(datasets_used),
        "",
        "## Dataset source URLs",
        "",
    ]
    lines.extend([f"- {url}" for url in source_urls])
    lines.extend(
        [
            "",
            "## Rows processed",
            "",
            f"- rows_processed: {rows_processed}",
            f"- accepted_rows: {accepted_rows}",
            f"- rejected_rows: {rejected_rows}",
            "",
            "## Mapped fields",
            "",
            ", ".join(mapped_fields),
            "",
            "## Decision distribution",
            "",
            json.dumps(decision_distribution, indent=2),
            "",
            "## Replay success rate",
            "",
            f"{replay_success_rate:.6f}",
            "",
            "## Audit-chain verification",
            "",
            ("skipped" if audit_chain_valid is None else str(audit_chain_valid).lower()),
            "",
            "## Evidence pack mode",
            "",
            f"- mode: {evidence_pack_mode}",
        ]
    )
    if evidence_pack_rows is not None:
        lines.append(f"- sampled_rows: {evidence_pack_rows}")
    lines.extend(
        [
            "",
            "## Fairness/segment diagnostics",
            "",
            json.dumps(fairness_summary, indent=2),
            "",
            "## Limitations",
            "",
            "- Disclosure-field mappings are proxy transformations and not underwriting truth labels.",
            "- CRT outcomes here are governance proxies and not production credit eligibility outputs.",
            "- Results are for C-DAG explainability validation, not regulatory or legal certification.",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Public CRT loan-level validation.")
    parser.add_argument(
        "--input",
        "--normalized-input",
        dest="inputs",
        action="append",
        required=True,
        help="Normalized CRT CSV path from prepare_fannie_cas.py or prepare_freddie_stacr.py. Repeat to combine datasets.",
    )
    parser.add_argument(
        "--model-config",
        default=str(ROOT / "configs" / "public_crt_model.v1.json"),
        help="Base CRT model config path.",
    )
    parser.add_argument(
        "--policy-config",
        default=str(ROOT / "configs" / "public_crt_policy.v1.json"),
        help="CRT policy config path.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "validation" / "outputs" / "public_crt_validation"),
        help="Output directory for CRT validation artifacts.",
    )
    parser.add_argument("--max-audits", type=int, default=100, help="Maximum decision-level audit traces to generate.")
    parser.add_argument("--subgroup-column", default="segment", help="Subgroup column for fairness diagnostics.")
    parser.add_argument("--skip-evidence-pack", action="store_true", help="Skip evidence-pack export.")
    parser.add_argument(
        "--evidence-pack-max-rows",
        type=int,
        default=None,
        help="Optional cap on rows used for evidence-pack export.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.evidence_pack_max_rows is not None and args.evidence_pack_max_rows <= 0:
        raise ValueError("--evidence-pack-max-rows must be a positive integer")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _progress("loading inputs")
    all_rows: list[dict[str, str]] = []
    datasets_used: list[str] = []
    source_urls: list[str] = []
    for raw_path in args.inputs:
        rows = _read_csv_rows(Path(raw_path))
        all_rows.extend(rows)
        dataset_names = sorted({row.get("source_dataset", "") for row in rows if row.get("source_dataset", "")})
        datasets_used.extend(dataset_names)
        for name in dataset_names:
            url = DATASET_SOURCE_URLS.get(name)
            if url:
                source_urls.append(url)

    valid_rows, rejected_rows = _validate_rows(all_rows)
    if not valid_rows:
        raise ValueError("No valid normalized CRT rows available after filtering.")

    _progress("combining normalized rows")
    combined_path = output_dir / "combined_normalized.csv"
    combined_fields = sorted({key for row in valid_rows for key in row.keys()})
    _write_csv(combined_path, combined_fields, valid_rows)

    _progress("estimating draft CPDs")
    cpd_rows = [
        {
            "leverage_risk": row["leverage_risk"],
            "borrower_credit_risk": row["borrower_credit_risk"],
            "loan_performance_risk": row["loan_performance_risk"],
            "property_or_pool_segment": row["property_or_pool_segment"],
            "delinquency_or_loss_proxy": row["delinquency_or_loss_proxy"],
            "crt_escalation_risk": row["crt_escalation_risk"],
        }
        for row in valid_rows
    ]
    source_dataset_reference = ";".join(
        sorted({row.get("source_dataset", "") for row in valid_rows if row.get("source_dataset", "")})
    )
    draft_config = build_draft_model_config(
        base_model_config_path=args.model_config,
        rows=cpd_rows,
        source_dataset_reference=source_dataset_reference or "public_crt_inputs",
        notes="Draft CPD estimate from public CRT loan-level validation rows.",
    )
    draft_model_path = output_dir / "draft_model_config.public_crt.json"
    draft_model_path.write_text(json.dumps(draft_config, indent=2), encoding="utf-8")

    _progress("running batch decisions")
    batch_input_rows = [
        {
            "tenant_id": row.get("tenant_id", "default") or "default",
            "leverage_risk": row["leverage_risk"],
            "borrower_credit_risk": row["borrower_credit_risk"],
            "property_or_pool_segment": row["property_or_pool_segment"],
            args.subgroup_column: row.get(args.subgroup_column, "unspecified") or "unspecified",
        }
        for row in valid_rows
    ]
    batch_input_path = output_dir / "batch_input.csv"
    _write_csv(
        batch_input_path,
        ["tenant_id", "leverage_risk", "borrower_credit_risk", "property_or_pool_segment", args.subgroup_column],
        batch_input_rows,
    )
    batch_output_path = output_dir / "batch_output.csv"
    batch_summary = run_batch_csv(
        model_config_path=draft_model_path,
        policy_config_path=args.policy_config,
        csv_input_path=batch_input_path,
        csv_output_path=batch_output_path,
        subgroup_column=args.subgroup_column,
    )
    batch_rows = _read_csv_rows(batch_output_path)
    decision_distribution = _decision_distribution(batch_rows)

    _progress("generating fairness report")
    fairness_report = compute_fairness_report(batch_rows, subgroup_column=args.subgroup_column, min_sample_size=30)
    fairness_path = output_dir / "fairness_report.json"
    fairness_path.write_text(json.dumps(fairness_report, indent=2), encoding="utf-8")

    _progress("generating audit traces")
    audit_traces: list[dict[str, Any]] = []
    replay_success = 0
    replay_checked = 0
    for row in valid_rows[: max(args.max_audits, 0)]:
        evidence = {
            "leverage_risk": row["leverage_risk"],
            "borrower_credit_risk": row["borrower_credit_risk"],
            "property_or_pool_segment": row["property_or_pool_segment"],
        }
        audit = run_decision(
            model_config_path=draft_model_path,
            policy_config_path=args.policy_config,
            evidence=evidence,
            intervention_scenarios=DEFAULT_COUNTERFACTUALS,
            tenant_id=row.get("tenant_id", "default") or "default",
        ).to_dict()
        audit["source_record_id"] = row.get("source_record_id", "")
        audit["source_dataset"] = row.get("source_dataset", "")
        audit_traces.append(audit)

        replay_checked += 1
        replay = replay_from_audit_payload(
            audit_payload=audit,
            model_config_path=draft_model_path,
            policy_config_path=args.policy_config,
        )
        if replay.get("risk_probability_match") and replay.get("decision_match"):
            replay_success += 1

    replay_success_rate = (replay_success / replay_checked) if replay_checked else 0.0
    audit_traces_path = output_dir / "audit_traces.json"
    audit_traces_path.write_text(json.dumps(audit_traces, indent=2), encoding="utf-8")

    evidence_pack_mode = "skipped" if args.skip_evidence_pack else "full"
    evidence_pack_rows: int | None = None
    evidence_pack_metadata: dict[str, Any] | None = None
    audit_chain_valid: bool | None = None
    if not args.skip_evidence_pack:
        _progress("exporting evidence pack")
        evidence_pack_dir = output_dir / "evidence_pack"
        evidence_input_path = batch_input_path
        if args.evidence_pack_max_rows is not None:
            evidence_pack_mode = "sampled"
            evidence_pack_rows = min(args.evidence_pack_max_rows, len(batch_input_rows))
            evidence_input_path = output_dir / "evidence_pack_input.sampled.csv"
            _write_csv(
                evidence_input_path,
                ["tenant_id", "leverage_risk", "borrower_credit_risk", "property_or_pool_segment", args.subgroup_column],
                batch_input_rows[:evidence_pack_rows],
            )
        evidence_pack_metadata = export_evidence_pack(
            input_csv=evidence_input_path,
            output_dir=evidence_pack_dir,
            model_config_path=draft_model_path,
            policy_config_path=Path(args.policy_config),
        )
        chain_rows = json.loads((evidence_pack_dir / "audit_chain.json").read_text(encoding="utf-8"))
        audit_chain_valid = verify_audit_chain(chain_rows)

    _progress("writing report")
    report_path = output_dir / "crt_validation_report.generated.md"
    _write_report(
        report_path=report_path,
        datasets_used=sorted(set(datasets_used)),
        source_urls=sorted(set(source_urls)),
        rows_processed=len(all_rows),
        accepted_rows=len(valid_rows),
        rejected_rows=rejected_rows,
        decision_distribution=decision_distribution,
        replay_success_rate=replay_success_rate,
        audit_chain_valid=audit_chain_valid,
        evidence_pack_mode=evidence_pack_mode,
        evidence_pack_rows=evidence_pack_rows,
        mapped_fields=list(REQUIRED_COLUMNS),
        fairness_summary={
            "subgroup_column": fairness_report.get("subgroup_column"),
            "rows_analyzed": fairness_report.get("rows_analyzed"),
            "max_min_subgroup_delta": fairness_report.get("max_min_subgroup_delta"),
            "warnings": fairness_report.get("warnings"),
        },
    )

    summary = {
        "status": "completed",
        "output_dir": str(output_dir),
        "rows_processed": len(all_rows),
        "accepted_rows": len(valid_rows),
        "rejected_rows": rejected_rows,
        "datasets_used": sorted(set(datasets_used)),
        "mapped_fields": list(REQUIRED_COLUMNS),
        "decision_distribution": decision_distribution,
        "replay_success_rate": replay_success_rate,
        "audit_chain_valid": audit_chain_valid,
        "evidence_pack_mode": evidence_pack_mode,
        "evidence_pack_rows": evidence_pack_rows,
        "evidence_pack": evidence_pack_metadata,
        "draft_model_config": str(draft_model_path),
        "batch_summary": batch_summary,
        "fairness_report": str(fairness_path),
        "audit_traces": str(audit_traces_path),
        "validation_report": str(report_path),
        "non_production_disclaimer": (
            "Public CRT loan-level validation. "
            "Not production validation, not consumer credit eligibility, and not regulatory compliance proof."
        ),
    }
    summary_path = output_dir / "validation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
