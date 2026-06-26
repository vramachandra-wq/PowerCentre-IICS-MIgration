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

## Central Repository Tables in SQL

| Table | Purpose |
|---|---|
| `assets` | Master inventory for mappings, sources, targets, and transformations |
| `mappings` | Mapping-level migration scope, sources, targets, counts, and complexity |
| `transformations` | Transformation-level technical logic inside mappings |
| `columns_metadata` | Source and target column metadata for datatype and rule checks |
| `sql_overrides` | SQL override text requiring migration compatibility review |
| `connectors` | Port-to-port and component-to-component data-flow links |
