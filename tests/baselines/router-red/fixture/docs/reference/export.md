# Export behavior

- Output is CSV, one file per tenant.
- Newline handling is explicit: the writer opens files in binary mode
  (`src/export.py:4`).
