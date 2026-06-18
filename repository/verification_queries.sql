USE pc_iics_migration;

SHOW TABLES;

SELECT COUNT(*) AS asset_count
FROM assets;

SELECT COUNT(*) AS mapping_count
FROM mappings;

SELECT COUNT(*) AS transformation_count
FROM transformations;

SELECT COUNT(*) AS column_count
FROM columns_metadata;

SELECT COUNT(*) AS sql_override_count
FROM sql_overrides;

SELECT COUNT(*) AS connector_count
FROM connectors;

SELECT complexity, COUNT(*) AS mapping_count
FROM mappings
GROUP BY complexity
ORDER BY complexity;

SELECT asset_name, asset_type, source_file, complexity
FROM assets
ORDER BY asset_type, asset_name
LIMIT 100;

SELECT mapping_name, transformation_count, connector_count, sql_override_count, complexity
FROM mappings
ORDER BY complexity DESC, transformation_count DESC;

SELECT mapping_name, transformation_name, transformation_type
FROM transformations
ORDER BY mapping_name, transformation_name
LIMIT 200;
