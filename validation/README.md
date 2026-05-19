# Public Institutional Loan-Level Validation

This directory defines the **public institutional loan-level validation** path for `causal-credit-risk-engine`.

Scope:

- Uses public institutional mortgage datasets only.
- Uses local files downloaded by the operator.
- Normalizes source fields into causal engine-compatible variables.
- Runs draft CPD estimation, batch decisions, fairness diagnostics, audit traces, replay checks, and evidence-pack export.

Hard boundaries:

- No customer data.
- No PII required.
- No production-validation claims.
- No changes to core inference math.
- No changes to reference demo CPDs.

## Layout

```text
validation/
  README.md
  data_sources.md
  mortgage_feature_mapping.md
  validation_plan.md
  public_institutional_validation_report.md
  limitations.md
  examples/
    expected_schema_freddie_mac.json
    expected_schema_fannie_mae.json
    expected_schema_hmda.json
    expected_schema_fhfa.json
  outputs/                # generated locally, gitignored
```

## Scripts

- `scripts/prepare_freddie_mac.py`
- `scripts/prepare_fannie_mae.py`
- `scripts/prepare_hmda.py`
- `scripts/prepare_fhfa.py`
- `scripts/run_public_mortgage_validation.py`

All scripts accept local input paths and write normalized CSVs under `validation/outputs/` by default.
