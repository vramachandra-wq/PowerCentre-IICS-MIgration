# PowerCenter to IICS Metadata Migration Accelerator

This repository provides an enterprise metadata extraction and analysis framework for **PowerCenter to IICS migration** activities.

It reads PowerCenter XML exports, extracts technical metadata, builds a normalized canonical metadata model, evaluates mapping complexity, generates migration reports, and stores processed metadata in a MySQL repository for future PowerCenter-vs-IICS comparison.

## Table Of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Running The Application](#running-the-application)
- [Generated Outputs](#generated-outputs)
- [Database Scripts](#database-scripts)
- [Central Repository Tables](#central-repository-tables)

## Features

- Config-driven XML ingestion from `input_xml`
- PowerCenter metadata extraction for repositories, folders, workflows, sessions, mappings, sources, targets, transformations, ports, connectors, instances, and SQL overrides
- Canonical metadata model for downstream processing
- Mapping complexity classification
- Enterprise migration reports
- MySQL-based central metadata repository
- MySQL Workbench scripts for schema creation, loading, and validation
- CLI-based execution for individual stages and full pipeline orchestration



## Project Structure upto enterprise level:

```text
pc_iics_migration/
|-- app.py
|-- api/
|   |-- routes/
|   |-- schemas/
|-- business/
|   |-- parser/
|   |-- validation/
|   |-- complexity/
|   |-- lineage/
|   |-- recommendation/
|   |-- migration/
|-- data/
|   |-- repositories/
|   |-- models/
|   |-- database/
|-- common/
|   |-- constants/
|   |-- exceptions/
|   |-- logger/
|   |-- utils/
|   |-- config/
|-- reports/
|-- tests/
|-- input_xml/
|-- output/
|-- requirements.txt
```

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Place PowerCenter XML exports in:

```text
input_xml/
```

Runtime configuration is stored in:

```text
common/config/config.json
```
## Generated Outputs

### Parsed Metadata

```text
output/metadata_tables/
output/parsed_json/
output/parser_batch_summary.json
```

### Canonical Metadata

```text
output/canonical/
|-- tables/
|-- mapping_json_by_id/
|-- canonical_mappings.json
|-- canonical_summary.json
```

### Enterprise Reports

```text
output/enterprise/
|-- asset_inventory.csv
|-- transformation_type_summary.csv
|-- mapping_migration_catalog.csv
|-- executive_summary.json
|-- enterprise_migration_report.md
```

### Complexity Reports

```text
output/complexity_classification_report.csv
output/complexity_classification_report.md
```git 

## Database Scripts

```text
data/database/
|-- schema.sql
|-- mysql_workbench_full_load.sql
|-- verification_queries.sql
```

Use `data/database/mysql_workbench_full_load.sql` in MySQL Workbench to create the schema and insert metadata.

Use `data/database/verification_queries.sql` to validate table counts and inspect loaded data.

## REST APIs

Start the FastAPI application:

```bash
uvicorn app:create_app --factory --reload
```

Health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Start a complete migration from `input_xml/`:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/migrate \
  -H "Content-Type: application/json" \
  -d '{"use_input_folder": true}'
```

Start a migration with uploaded XML content:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/migrate \
  -H "Content-Type: application/json" \
  -d '{"uploaded_xml_name": "sample.xml", "uploaded_xml_content": "<POWERMART></POWERMART>"}'
```

Sample migration response:

```json
{
  "job_id": "7b2d8f7e4d0f4e6c9c8f6b3b0f1b0a11",
  "status": "Completed",
  "readiness_score": 96.42,
  "validation_summary": {
    "total_issues": 42,
    "open_issues": 3,
    "resolved_issues": 39,
    "severity_counts": {
      "HIGH": 4,
      "MEDIUM": 30,
      "LOW": 8
    }
  },
  "auto_fix_accuracy": 92.5,
  "generated_report_locations": {
    "validation_report": "output/validation_report.csv",
    "remediation_report": "output/remediation_report.csv",
    "dashboard_dataset_json": "output/automation/dashboard_dataset.json"
  },
  "iics_deployment": {
    "provider": "MockIICSProvider",
    "status": {
      "state": "COMPLETED"
    }
  }
}
```

Check job progress:

```bash
curl http://127.0.0.1:8000/api/v1/jobs/{job_id}
```

List generated reports:

```bash
curl http://127.0.0.1:8000/api/v1/reports/{job_id}
```

Return the dashboard dataset for Streamlit:

```bash
curl http://127.0.0.1:8000/api/v1/dashboard/{job_id}
```

The REST controllers are intentionally thin. They validate API input, call `MigrationOrchestrator`, and return response models. The orchestrator coordinates the existing parser, canonical repository builder, complexity classifier, datatype harmonization, validation, rule-based remediation, readiness/risk/effectiveness reports, automation datasets, and the pluggable `IICSAdapter`.

IICS deployment defaults to `MockIICSProvider`, which performs no external API calls. Set `IICS_PROVIDER=real` only after implementing the TODO methods in `RealIICSProvider`.

## Central Repository Tables in SQL

| Table | Purpose |
|---|---|
| `assets` | Master inventory for mappings, sources, targets, and transformations |
| `mappings` | Mapping-level migration scope, sources, targets, counts, and complexity |
| `transformations` | Transformation-level technical logic inside mappings |
| `columns_metadata` | Source and target column metadata for datatype and rule checks |
| `sql_overrides` | SQL override text requiring migration compatibility review |
| `connectors` | Port-to-port and component-to-component data-flow links |
