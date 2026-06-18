# PowerCenter to IICS Enterprise Metadata Accelerator

This repository provides an enterprise-ready metadata foundation for PowerCenter to IICS migration planning. It parses PowerCenter XML exports, builds normalized metadata, classifies mapping complexity, generates stakeholder reports, and loads a central MySQL repository for future PowerCenter-vs-IICS comparison.

## Enterprise Capabilities

- Config-driven XML ingestion from `input_xml`
- Raw metadata extraction for repositories, folders, workflows, sessions, mappings, sources, targets, transformations, ports, connectors, instances, and SQL overrides
- Canonical metadata model for stable downstream comparison
- Rule-based mapping complexity classification
- Enterprise report generation for stakeholders and engineering teams
- Central MySQL repository with normalized tables
- MySQL Workbench scripts for schema, inserts, and verification
- Single-command orchestration for repeatable migration assessment runs

## Architecture

```text
PowerCenter XMLs
  -> Parser Layer
  -> Raw Metadata Tables
  -> Canonical Builder
  -> Complexity Classifier
  -> Enterprise Reports
  -> MySQL Metadata Repository
  -> Future PowerCenter vs IICS Comparator
```

More detail:

- [Enterprise Architecture](docs/enterprise_architecture.md)
- [Data Model](docs/data_model.md)
- [Complexity Rules](docs/mapping_complexity_rules.md)
- [Operations Runbook](docs/operations_runbook.md)

## Folder Structure

```text
project_root/
|-- config/          Runtime path, logging, and MySQL configuration
|-- docs/            Enterprise architecture and operations documentation
|-- extractor/       Metadata enrichment, including complexity classification
|-- input_xml/       PowerCenter XML exports
|-- logs/            Application logs
|-- parser/          XML parsing framework
|-- reports/         Generated metadata, canonical outputs, and enterprise reports
|-- repository/      Canonical model and MySQL persistence layer
|-- services/        End-to-end enterprise orchestration
|-- utils/           Shared config and logging utilities
|-- main.py          CLI entry point
```

## Setup

```bash
pip install -r requirements.txt
```

Review database and path settings:

```text
config/config.json
```

## Enterprise Commands

Run the full enterprise pipeline:

```bash
python main.py --mode enterprise
```

Run the full pipeline and refresh MySQL:

```bash
python main.py --mode enterprise --persist
```

Regenerate reports from existing metadata:

```bash
python main.py --mode reports
```

Refresh MySQL from existing canonical outputs:

```bash
python main.py --mode persist
```

Run only canonical build:

```bash
python main.py
```

Run only raw parser:

```bash
python main.py --mode parse
```

Run only complexity classifier:

```bash
python main.py --mode classify
```

Explore XML structure:

```bash
python main.py --mode explore --print-hierarchy
```

## Generated Outputs

Raw parsed metadata:

```text
reports/metadata_tables/
reports/parsed_json/
reports/parser_batch_summary.json
```

Canonical repository outputs:

```text
reports/canonical/tables/
reports/canonical/mapping_json_by_id/
reports/canonical/canonical_mappings.json
reports/canonical/canonical_summary.json
```

Enterprise reports:

```text
reports/enterprise/asset_inventory.csv
reports/enterprise/transformation_type_summary.csv
reports/enterprise/mapping_migration_catalog.csv
reports/enterprise/executive_summary.json
reports/enterprise/enterprise_migration_report.md
```

Complexity reports:

```text
reports/complexity_classification_report.csv
reports/complexity_classification_report.md
```

MySQL Workbench assets:

```text
repository/schema.sql
repository/mysql_workbench_full_load.sql
repository/verification_queries.sql
```

## Central Repository Tables

The MySQL repository stores metadata by domain, not by XML file:

| Table | Purpose |
|---|---|
| `assets` | Master inventory for mappings, sources, targets, and transformations |
| `mappings` | Mapping-level migration scope, counts, sources, targets, and complexity |
| `transformations` | Transformation-level technical logic |
| `columns_metadata` | Source and target field metadata for datatype checks |
| `sql_overrides` | SQL override text and review status |
| `connectors` | Data-flow and lineage links inside mappings |

The 14 XML files are inputs. The six MySQL tables are normalized enterprise metadata categories. Every row retains traceability through XML/source file, repository, folder, mapping, and generated IDs.

## Complexity Model

Report labels:

```text
Simple
Medium
Complex
```

Canonical repository labels:

```text
LOW
MEDIUM
HIGH
```

Business mapping:

| Report | Repository | Meaning |
|---|---|---|
| Simple | LOW | Lower migration effort |
| Medium | MEDIUM | Needs validation and targeted review |
| Complex | HIGH | Needs detailed analysis and possible remediation |

Complexity is calculated from transformation count, lookups, SQL overrides, expression logic, filters/routers, stored procedures, mapplets, and advanced transformation types.

## Current Scope

The current implementation is focused on PowerCenter source metadata. The repository is intentionally shaped so IICS target metadata can later be loaded into the same comparison model.
