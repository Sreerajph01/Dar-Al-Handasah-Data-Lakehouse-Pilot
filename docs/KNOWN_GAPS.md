# Known Gaps

## M2 Close-out Debt
Deadline: Before M4 starts.

- run the gate through `make verify` and a second `make seed` on the same stack (not run_all.ps1)
- evidence of the nine DAR_DW tables, columns and `small`-scale row counts
- seeded DQ issues counted in the source and shown unmodified in Bronze
- D365 OData (pagination and $filter) and SharePoint list/delta endpoint responses
- DAG run IDs and per-task states proving dlt for all three sources
- Bronze audit columns and the watermark table
- per-table, per-source expected vs actual appended rows, and soft-delete assertions (both views, plus an incremental delete of an existing row)
- STATIC_TABLES documented with a reason, and a test or gap entry for a late-corrected static row
- proof that gate tests FAIL/SKIP (never PASS) on caught errors
- RFP xlsx parse (no embedded fallback), image-tag check for images not yet started, full docker stats total
