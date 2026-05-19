# Validation Plan

Objective: run **public institutional loan-level validation** without changing inference math or reference CPDs.

## Pipeline

1. Prepare source datasets into normalized CSV:
   - Freddie: `scripts/prepare_freddie_mac.py`
   - Fannie: `scripts/prepare_fannie_mae.py`
   - HMDA: `scripts/prepare_hmda.py`
   - FHFA: `scripts/prepare_fhfa.py`

2. Run validation workflow:
   - `python scripts/run_public_mortgage_validation.py --normalized-input <file> [--normalized-input <file> ...]`

3. Workflow actions:
   - load normalized rows
   - estimate draft CPDs
   - run batch decisions
   - compute fairness diagnostics
   - generate decision-level audit traces
   - run deterministic replay checks
   - verify audit-chain integrity
   - export evidence pack
   - write validation report

## Verification checks

- Existing project tests pass.
- Default CLI example still returns `risk_probability = 0.849375`.
- No generated validation outputs committed.
- Validation report includes source URLs, mapping assumptions, limitations, and non-production disclaimer.

## Output location

- `validation/outputs/` (gitignored)
