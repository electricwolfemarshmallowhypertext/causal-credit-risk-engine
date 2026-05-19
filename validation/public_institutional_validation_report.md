# Public Institutional Loan-Level Validation Report (Template)

Use this template when documenting a run from `scripts/run_public_mortgage_validation.py`.

## Non-production disclaimer

This report is for **public institutional loan-level validation** only. It is not production model validation, not credit policy approval, and not legal/regulatory certification.

## Dataset used

- Freddie Mac Single-Family Loan-Level Dataset
- Fannie Mae Single-Family Loan Performance Data
- HMDA / CFPB mortgage data
- FHFA Public Use Database

## Dataset source URLs

- https://www.freddiemac.com/research/datasets/sf-loanlevel-dataset
- https://www.freddiemac.com/fmac-resources/research/pdf/user_guide.pdf
- https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/fannie-mae-single-family-loan-performance-data
- https://ffiec.cfpb.gov/
- https://www.fhfa.gov/pudbdata

## Required report sections

1. Dataset used
2. Row count
3. Fields mapped
4. CPD estimation summary
5. Decision distribution
6. Replay success rate
7. Audit-chain verification result
8. Fairness diagnostic summary
9. Limitations
10. Mapping assumptions
11. Non-production disclaimer

## Facts to anchor

- Freddie Mac provides loan-level origination, monthly performance, and actual loss data.
- Fannie Mae provides single-family acquisition and performance data.
- HMDA is CFPB's comprehensive public source for U.S. mortgage-market application data.
- FHFA public-use data includes income, race, sex, tract, LTV, mortgage age, and affordability-related fields.
