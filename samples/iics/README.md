# IICS Import Package Sample

This folder contains a **tracked sample** of the generated IICS import package so reviewers can download it from the PR without running the pipeline locally.

The main `output/` folder remains gitignored because it holds ephemeral logs and reports from every run.

## Files

| File | Description |
|---|---|
| `iics_generated_package_checksum.zip` | Import-ready IICS export (73 assets, native CDI format) |
| `generation_summary.json` | Asset counts and generation metadata |

## Regenerate locally

```powershell
python app.py --mode parse
python app.py --mode iics-package
```

Output is written to `output/iics_generated/iics_generated_package_checksum.zip`.

## IICS import

1. Upload `iics_generated_package_checksum.zip` in IICS **Admin → Import**.
2. Keep **Project**, **Folder**, and all mapping assets selected.
3. Deselect **Connection** / **Agent Group** if they already exist in your org.
4. Map **`DBConnection_OLAP`** to your Oracle connection when prompted.

## Update this sample

After regenerating and validating:

```powershell
Copy-Item output/iics_generated/iics_generated_package_checksum.zip samples/iics/
Copy-Item output/iics_generated/generation_summary.json samples/iics/
```
