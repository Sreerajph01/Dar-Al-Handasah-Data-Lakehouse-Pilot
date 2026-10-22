#!/usr/bin/env python3
"""
tests/traceability/check_traceability.py
"""
import pathlib
import sys
import yaml
import csv
import pandas as pd

REPO_ROOT         = pathlib.Path(__file__).parent.parent.parent
REQUIREMENTS_FILE = REPO_ROOT / "docs" / "rfp" / "requirements.yaml"
COVERAGE_CSV      = REPO_ROOT / "docs" / "rfp" / "coverage.csv"
TRACEABILITY_MD   = REPO_ROOT / "docs" / "rfp" / "TRACEABILITY.md"
XLSX_FILE         = REPO_ROOT / "docs" / "source" / "RFP_tooling.xlsx"

def parse_xlsx():
    print(f"Reading from {XLSX_FILE}")
    if not XLSX_FILE.exists():
        print(f"ERROR: RFP file missing at {XLSX_FILE}")
        sys.exit(1)

    xl = pd.ExcelFile(XLSX_FILE)
    df = xl.parse(xl.sheet_names[0])

    parsed = []
    errors = []

    for idx, row in df.iterrows():
        try:
            nb = str(row['Nb']).strip()
            if nb == 'nan':
                continue

            req_id = f"RFP-{int(float(nb)):02d}"

            parsed.append({
                "id": req_id,
                "area": str(row.get('Major Section', '')).strip(),
                "text": str(row.get('Requirement', '')).strip(),
                "status": str(row.get('Compliance', 'Not yet verified')).strip(),
                "component": str(row.get('Open-Source Option', '')).strip() if pd.notna(row.get('Open-Source Option')) else "TBD",
                "classification": "Documented"
            })
        except Exception as e:
            errors.append((idx, str(e)))

    if errors:
        print("ERROR: Failed to parse some rows:")
        for idx, err in errors:
            print(f"Row {idx}: {err}")
        sys.exit(1)

    print(f"Successfully parsed {len(parsed)} requirements from sheet '{xl.sheet_names[0]}'.")
    print(f"Total rows in sheet: {len(df)}. Columns: {list(df.columns)}")

    with open(REQUIREMENTS_FILE, "w", encoding="utf-8") as f:
        yaml.dump({"requirements": parsed}, f, sort_keys=False)

    return parsed

def generate_reports(requirements):
    # Create CSV
    with open(COVERAGE_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Area", "Requirement", "Status", "Component", "Class"])
        for req in requirements:
            writer.writerow([req['id'], req['area'], req['text'], req['status'], req['component'], req['classification']])

    # Create MD
    md = [
        "# RFP Traceability Matrix",
        "",
        "Generated from: `docs/source/RFP_tooling.xlsx`",
        "",
        "| ID | Area | Requirement | Status | Component | Class |",
        "|---|---|---|---|---|---|"
    ]

    for req in requirements:
        md.append(f"| {req['id']} | {req['area']} | {req['text']} | {req['status']} | {req['component']} | {req['classification']} |")

    with open(TRACEABILITY_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"Wrote {COVERAGE_CSV}")
    print(f"Wrote {TRACEABILITY_MD}")

def main():
    requirements = parse_xlsx()
    generate_reports(requirements)
    print("M1 Traceability mapping completed!")

if __name__ == "__main__":
    main()
