# Running the UAD 3.6 QC app (local)

## One-time setup
1. Install Python 3.12+ and Node 20+.
2. `python -m venv backend\.venv`
3. `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
4. `npm --prefix frontend install`

## Every time
Run `.\dev.ps1` from the project folder, then open http://localhost:8000

## Try it
Upload `Sample reports\SF1_Appraisal_v1.4.zip`. You should see:
- run metadata (schema + ruleset versions),
- a purple "Schema / structural issues" box if the file has XSD violations
  (possible — samples are v1.4, schema is v1.3),
- a green "No issues found" box (the 4 seed rules pass on this sample).

Toggle Appraiser / QD Reviewer — reviewer mode shows citations and rule errors.

## Tests
`backend\.venv\Scripts\python.exe -m pytest backend/tests -v`

## Versions on every run
- `schema_version` comes from the active SchemaAdapter (`GSE_UAD_3.6.0_v1.3`).
- `ruleset_version` = ruleset name + content hash of `rules\seed_rules.json`;
  editing the file changes the recorded version automatically.
