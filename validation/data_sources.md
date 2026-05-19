# Data Sources

This validation path is restricted to public institutional mortgage datasets.

## 1. Freddie Mac Single-Family Loan-Level Dataset

Primary URLs:

- https://www.freddiemac.com/research/datasets/sf-loanlevel-dataset
- https://www.freddiemac.com/fmac-resources/research/pdf/user_guide.pdf

Use in this project:

- Origination + monthly performance + delinquency/default/loss-oriented fields for performance-oriented validation.

Download instructions:

1. Open the dataset page above.
2. Register/sign in to the Freddie Mac data portal (Clarity Data Intelligence) if required.
3. Download one origination file and one monthly performance file for the same cohort/vintage.
4. Store files locally (do not commit).
5. Run:
   `python scripts/prepare_freddie_mac.py --origination-input <path> --performance-input <path>`

## 2. Fannie Mae Single-Family Loan Performance Data

Primary URL:

- https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/fannie-mae-single-family-loan-performance-data

Use in this project:

- Acquisition + monthly performance data for performance-oriented validation.

Download instructions:

1. Open the dataset page above.
2. Sign in / accept terms as required by Fannie Mae.
3. Download acquisition and performance files for a matching release period.
4. Store files locally (do not commit).
5. Run:
   `python scripts/prepare_fannie_mae.py --acquisition-input <path> --performance-input <path>`

## 3. HMDA / CFPB Mortgage Data

Primary URLs:

- https://ffiec.cfpb.gov/
- https://ffiec.cfpb.gov/data-publication/

Use in this project:

- Application/action/demographic/geography fields for fairness and decision-disparity diagnostics.

Download instructions:

1. Open the HMDA portal.
2. Select desired year and export the loan/application register dataset (or official public publication file).
3. Save CSV locally (do not commit).
4. Run:
   `python scripts/prepare_hmda.py --input <path_to_hmda_csv>`

## 4. FHFA Public Use Database (Enterprise PUDB)

Primary URLs:

- https://www.fhfa.gov/pudbdata
- https://www.fhfa.gov/data/dashboard/enterprise-single-family-public-use-database

Use in this project:

- Enterprise public mortgage fields including income, race, sex, tract, LTV, mortgage age, and affordability for fairness and validation diagnostics.

Download instructions:

1. Open the PUDB page.
2. Download the relevant single-family CSV files (National and/or Census Tract file based on analysis scope).
3. Save CSV locally (do not commit).
4. Run:
   `python scripts/prepare_fhfa.py --input <path_to_fhfa_csv>`

## Compliance reminder

This repository does not auto-download dataset files. Operators must obtain datasets directly from official sources and comply with source terms, licensing, and usage constraints.
