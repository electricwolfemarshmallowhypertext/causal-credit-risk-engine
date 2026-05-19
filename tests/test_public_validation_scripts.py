from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_pipe_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="|")
        writer.writerow(headers)
        writer.writerows(rows)


def test_prepare_scripts_generate_normalized_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        freddie_orig = tmp_dir / "freddie_orig.txt"
        freddie_perf = tmp_dir / "freddie_perf.txt"
        freddie_out = tmp_dir / "freddie_norm.csv"
        _write_pipe_csv(
            freddie_orig,
            [
                "loan_sequence_number",
                "original_loan_to_value",
                "original_combined_loan_to_value",
                "original_debt_to_income_ratio",
                "credit_score",
                "property_state",
            ],
            [
                ["L1", "82", "85", "45", "720", "TX"],
                ["L2", "70", "72", "35", "650", "CA"],
            ],
        )
        _write_pipe_csv(
            freddie_perf,
            ["loan_sequence_number", "current_loan_delinquency_status", "loan_age", "zero_balance_code"],
            [
                ["L1", "4", "36", ""],
                ["L2", "0", "12", ""],
            ],
        )

        result_freddie = _run(
            [
                "scripts/prepare_freddie_mac.py",
                "--origination-input",
                str(freddie_orig),
                "--performance-input",
                str(freddie_perf),
                "--has-header",
                "--output",
                str(freddie_out),
            ]
        )
        assert result_freddie.returncode == 0, result_freddie.stderr
        assert freddie_out.exists()

        hmda_in = tmp_dir / "hmda.csv"
        hmda_out = tmp_dir / "hmda_norm.csv"
        hmda_in.write_text(
            "lei,action_taken,loan_purpose,state,county,census_tract,debt_to_income_ratio,combined_loan_to_value_ratio,applicant_race_1,applicant_sex\n"
            "XYZ,1,1,TX,201,12345678901,38,78,5,1\n"
            "XYZ,3,1,CA,001,09876543210,52,92,3,2\n",
            encoding="utf-8",
        )
        result_hmda = _run(
            [
                "scripts/prepare_hmda.py",
                "--input",
                str(hmda_in),
                "--output",
                str(hmda_out),
            ]
        )
        assert result_hmda.returncode == 0, result_hmda.stderr
        assert hmda_out.exists()

        fhfa_in = tmp_dir / "fhfa.csv"
        fhfa_out = tmp_dir / "fhfa_norm.csv"
        fhfa_in.write_text(
            "loan_id,income,race,sex,census_tract,ltv,debt_to_income_ratio,loan_age\n"
            "F1,120,5,1,12345678901,75,34,48\n",
            encoding="utf-8",
        )
        result_fhfa = _run(
            [
                "scripts/prepare_fhfa.py",
                "--input",
                str(fhfa_in),
                "--output",
                str(fhfa_out),
            ]
        )
        assert result_fhfa.returncode == 0, result_fhfa.stderr
        assert fhfa_out.exists()

        with freddie_out.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 2
        assert rows[0]["tenure"] in {"short", "long"}
        assert rows[0]["utilization"] in {"low", "high"}


def test_prepare_fannie_single_file_historical_performance_format() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        fannie_in = tmp_dir / "fannie_hp.csv"
        fannie_out = tmp_dir / "fannie_norm.csv"

        def _build_row(
            loan_id: str,
            reporting_period: str,
            upb: str,
            loan_age: str,
            current_ltv: str,
            current_cltv: str,
            dti: str,
            fico: str,
            state: str,
            delinquency: str,
        ) -> list[str]:
            row = [""] * 113
            row[0] = ""
            row[1] = loan_id
            row[2] = reporting_period
            row[9] = upb
            row[12] = "360"
            row[13] = "012020"
            row[14] = "022020"
            row[15] = loan_age
            row[16] = "300"
            row[18] = "012050"
            row[19] = current_ltv
            row[20] = current_cltv
            row[21] = "1"
            row[22] = dti
            row[23] = fico
            row[25] = "N"
            row[27] = "P"
            row[28] = "1"
            row[29] = "R"
            row[30] = state
            row[31] = "12345"
            row[32] = "606"
            row[33] = "0"
            row[34] = "FRM"
            row[39] = delinquency
            return row

        with fannie_in.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="|")
            writer.writerow(_build_row("0001", "042025", "91000.00", "60", "72", "75", "38", "720", "IL", "00"))
            writer.writerow(_build_row("0002", "042025", "120000.00", "12", "90", "92", "52", "640", "CA", "04"))

        result = _run(
            [
                "scripts/prepare_fannie_mae.py",
                "--input",
                str(fannie_in),
                "--max-rows",
                "2",
                "--output",
                str(fannie_out),
            ]
        )
        assert result.returncode == 0, result.stderr

        with fannie_out.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))

        assert len(rows) == 2
        assert rows[0]["source_dataset"] == "fannie_mae_sf_performance"
        assert rows[0]["source_record_id"] == "0001"
        assert rows[0]["tenure"] in {"short", "long"}
        assert rows[0]["utilization"] in {"low", "high"}
        assert rows[0]["risk"] in {"low_risk", "high_risk"}
        assert rows[1]["risk"] == "high_risk"


def test_public_validation_runner_executes_with_normalized_input() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        normalized = tmp_dir / "normalized.csv"
        normalized.write_text(
            "source_dataset,source_record_id,tenant_id,tenure,utilization,income,dsc,risk,segment\n"
            "freddie_mac_sf_loan_level,r1,default,short,high,unstable,below_threshold,high_risk,A\n"
            "fannie_mae_sf_performance,r2,default,long,low,stable,above_threshold,low_risk,B\n"
            "cfpb_hmda,r3,default,long,high,stable,below_threshold,high_risk,A\n",
            encoding="utf-8",
        )

        output_dir = tmp_dir / "validation_out"
        result = _run(
            [
                "scripts/run_public_mortgage_validation.py",
                "--normalized-input",
                str(normalized),
                "--output-dir",
                str(output_dir),
                "--max-audits",
                "3",
            ]
        )
        assert result.returncode == 0, result.stderr
        summary = json.loads((output_dir / "validation_summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "completed"
        assert summary["accepted_rows"] == 3
        assert "public institutional loan-level validation only" in summary["non_production_disclaimer"].lower()
