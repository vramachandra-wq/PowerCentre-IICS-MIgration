from __future__ import annotations

import argparse
from pathlib import Path

from utils.config_loader import ConfigLoader
from utils.logger import LoggerFactory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Explore Informatica PowerCenter XML exports and generate structure summaries."
    )
    parser.add_argument(
        "--mode",
        choices=["canonical", "parse", "explore"],
        default="canonical",
        help="Run canonical model build, raw metadata parser, or XML structure explorer.",
    )
    parser.add_argument(
        "--config",
        default="config/config.json",
        help="Path to JSON configuration file.",
    )
    parser.add_argument(
        "--xml-file",
        default=None,
        help="Optional single XML file to explore. Defaults to every XML in configured xml_folder.",
    )
    parser.add_argument(
        "--print-hierarchy",
        action="store_true",
        help="Print tag hierarchy to console in addition to writing report files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ConfigLoader(Path(args.config)).load()
    logger = LoggerFactory.create_logger(config.logging, config.paths.log_folder)

    if args.mode == "explore":
        from parser.xml_explorer import PowerCenterXmlExplorer

        explorer = PowerCenterXmlExplorer(config=config, logger=logger)
        if args.xml_file:
            summary = explorer.explore_file(Path(args.xml_file), print_hierarchy=args.print_hierarchy)
        else:
            summary = explorer.explore_folder(print_hierarchy=args.print_hierarchy)

        logger.info(
            "XML exploration completed. files=%s folders=%s mappings=%s unique_tags=%s",
            summary.file_count,
            len(summary.folder_summary),
            len(summary.mapping_summary),
            len(summary.tag_counts),
        )
    elif args.mode == "parse":
        from parser.xml_parser import XMLParser

        xml_parser = XMLParser(config=config, logger=logger)
        if args.xml_file:
            parsed = xml_parser.parse_file(Path(args.xml_file))
            xml_parser.json_output_folder.mkdir(parents=True, exist_ok=True)
            xml_parser.table_output_folder.mkdir(parents=True, exist_ok=True)
            xml_parser._write_json(parsed)
            tables = xml_parser.to_dataframes([parsed])
            xml_parser._write_tables(tables)
            logger.info("Metadata parsing completed for file=%s", parsed.file_name)
        else:
            result = xml_parser.parse_folder()
            logger.info(
                "Metadata parsing completed. files=%s errors=%s tables=%s",
                len(result["parsed_files"]),
                len(result["errors"]),
                len(result["dataframes"]),
            )
    else:
        from parser.xml_parser import XMLParser
        from repository.canonical_builder import CanonicalMetadataBuilder

        xml_parser = XMLParser(config=config, logger=logger)
        canonical_builder = CanonicalMetadataBuilder(config=config, logger=logger)
        if args.xml_file:
            parsed_files = [xml_parser.parse_file(Path(args.xml_file))]
        else:
            result = xml_parser.parse_folder()
            parsed_files = result["parsed_files"]
            if result["errors"]:
                logger.warning("Canonical build continuing with %s parser error(s)", len(result["errors"]))

        canonical_repository = canonical_builder.build(parsed_files)
        canonical_builder.write_outputs(canonical_repository)
        logger.info(
            "Canonical metadata build completed. assets=%s mappings=%s transformations=%s columns=%s connectors=%s sql_overrides=%s",
            len(canonical_repository.assets),
            len(canonical_repository.mappings),
            len(canonical_repository.transformations),
            len(canonical_repository.columns),
            len(canonical_repository.connectors),
            len(canonical_repository.sql_overrides),
        )


if __name__ == "__main__":
    main()
