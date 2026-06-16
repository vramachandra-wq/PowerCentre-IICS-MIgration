# PowerCenter to IDMC/IICS Post-Conversion Stabilization Accelerator

This POC establishes the Week 1 foundation for understanding Informatica PowerCenter XML exports before metadata extraction, complexity scoring, and canonical repository persistence are introduced.

Current scope:

- Scalable Python 3.13 project setup
- Config-driven XML input and report output paths
- Reusable PowerCenter XML exploration utility
- Reusable PowerCenter XML parser framework
- Canonical metadata model for PowerCenter assets
- XML tag inventory
- Unique Informatica component inventory
- Folder-level summary
- Mapping-level summary
- Structured metadata extraction for repositories, folders, workflows, sessions, mappings, sources, targets, transformations, connectors, instances, ports, and SQL overrides
- Normalized canonical repository outputs for future PowerCenter-vs-IICS comparison
- File and console logging

Database persistence is intentionally not implemented yet.

## Folder Structure

```text
project_root/
|-- input_xml/       PowerCenter XML exports used as parser input
|-- parser/          XML loading and exploration framework
|-- extractor/       Reserved for future enrichment modules
|-- repository/      Reserved for future SQLAlchemy/MySQL persistence layer
|-- reports/         Generated CSV, TXT, and JSON exploration outputs
|-- config/          Runtime configuration
|-- logs/            Application log files
|-- utils/           Shared config and logging utilities
|-- main.py          CLI entry point
```

## Tech Stack

- Python 3.13
- MySQL
- SQLAlchemy
- mysql-connector-python
- pandas
- lxml or xml.etree.ElementTree
- openpyxl
- Plotly
- JSON/dotenv-ready configuration

## Configuration

Update `config/config.json` before running in a new environment.

```json
{
  "database": {
    "host": "localhost",
    "port": 3306,
    "username": "root",
    "password": "change_me",
    "database": "pc_iics_migration",
    "driver": "mysql+mysqlconnector"
  },
  "paths": {
    "xml_folder": "input_xml",
    "output_folder": "reports",
    "log_folder": "logs"
  }
}
```

The database section is present for the future canonical metadata repository work. The current explorer does not connect to MySQL.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Place PowerCenter XML exports in `input_xml/`.

## Execution Examples

Explore all XML files in the configured folder:

```bash
python main.py
```

This runs the canonical metadata build by default. It parses all XML files, then writes normalized canonical outputs.

Run only the raw parser:

```bash
python main.py --mode parse
```

Run the parser for one XML file:

```bash
python main.py --xml-file input_xml/SDE_ORA_EmployeeDimension.XML
```

Explore all XML files and print the hierarchy to console:

```bash
python main.py --mode explore --print-hierarchy
```

Explore one XML file structure:

```bash
python main.py --mode explore --xml-file input_xml/SDE_ORA_EmployeeDimension.XML --print-hierarchy
```

## Generated Outputs

The parser writes one parsed JSON file per XML to:

- `reports/parsed_json/`

The parser writes structured metadata tables to `reports/metadata_tables/`:

- `repositories.csv`
- `folders.csv`
- `workflows.csv`
- `sessions.csv`
- `mappings.csv`
- `sources.csv`
- `source_columns.csv`
- `targets.csv`
- `target_columns.csv`
- `transformations.csv`
- `ports.csv`
- `connectors.csv`
- `instances.csv`
- `sql_overrides.csv`

The parser also writes:

- `reports/parser_batch_summary.json`

The canonical builder writes normalized repository outputs to:

- `reports/canonical/tables/canonical_assets.csv`
- `reports/canonical/tables/canonical_mappings.csv`
- `reports/canonical/tables/canonical_transformations.csv`
- `reports/canonical/tables/canonical_columns.csv`
- `reports/canonical/tables/canonical_connectors.csv`
- `reports/canonical/tables/canonical_sql_overrides.csv`
- `reports/canonical/mapping_json_by_id/`
- `reports/canonical/canonical_mappings.json`
- `reports/canonical/canonical_summary.json`

## Canonical Metadata Model

The canonical model standardizes PowerCenter XML metadata into comparison-ready structures. Future IDMC/IICS metadata can be transformed into the same schema and compared table-by-table.

Canonical asset table:

```text
asset_id, asset_name, asset_type, platform, repository_name, folder_name, source_file, parent_asset_id, complexity
```

Canonical mapping table:

```text
mapping_id, mapping_name, repository_name, folder_name, sources, targets, transformation_count, connector_count, sql_override_count, complexity
```

Canonical transformation table:

```text
transformation_id, mapping_id, mapping_name, transformation_name, transformation_type, reusable_flag, attribute_count, port_count
```

Canonical column table:

```text
column_id, asset_id, table_name, table_type, column_name, datatype, precision, scale, repository_name, folder_name, source_file
```

Canonical SQL override table:

```text
sql_override_id, mapping_id, mapping_name, context_type, context_name, sql_query
```

Canonical mapping JSON format:

```json
{
  "mapping_name": "M_EMPLOYEE",
  "sources": [],
  "targets": [],
  "transformations": [],
  "connectors": [],
  "sql_overrides": []
}
```

The explorer writes these files to `reports/`:

- `xml_tag_inventory.csv`
- `informatica_component_inventory.csv`
- `folder_level_summary.csv`
- `mapping_level_summary.csv`
- `xml_tag_hierarchy.txt`
- `metadata_summary.json`

Logs are written to `logs/pc_iics_migration.log` and to the console.

## Parser Classes

The reusable parser framework is organized as:

- `XMLParser`: batch orchestration, per-file JSON, and aggregate table outputs
- `MappingParser`: mappings, connectors, instances, and mapping metrics
- `WorkflowParser`: sessions, workflows, task instances, workflow links, and session SQL overrides
- `TransformationParser`: transformations, ports, table attributes, and transformation SQL overrides
- `SourceTargetParser`: source/target definitions and columns
- `CanonicalMetadataBuilder`: converts parsed metadata into normalized canonical repository tables and mapping JSON

## Notes

The parser extracts structural metadata only. It does not yet persist metadata into MySQL or calculate complexity scores. Those belong to the next implementation stage.
