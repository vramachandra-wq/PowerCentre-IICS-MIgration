CREATE DATABASE IF NOT EXISTS pc_iics_migration
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE pc_iics_migration;

CREATE TABLE assets (
    asset_id          VARCHAR(64) PRIMARY KEY,
    asset_name        VARCHAR(255) NOT NULL,
    asset_type        VARCHAR(50)  NOT NULL,
    platform          VARCHAR(50)  DEFAULT 'POWERCENTER',
    repository_name   VARCHAR(255),
    folder_name       VARCHAR(255),
    source_file       VARCHAR(255),
    parent_asset_id   VARCHAR(64),
    complexity        VARCHAR(10),
    migration_status  TINYINT DEFAULT NULL,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_asset_type (asset_type),
    INDEX idx_complexity (complexity),
    INDEX idx_migration_status (migration_status)
);

CREATE TABLE mappings (
    mapping_id            VARCHAR(64) PRIMARY KEY,
    mapping_name          VARCHAR(255) NOT NULL,
    repository_name       VARCHAR(255),
    folder_name           VARCHAR(255),
    source_file           VARCHAR(255),
    sources               TEXT,
    targets               TEXT,
    transformation_count  INT DEFAULT 0,
    connector_count       INT DEFAULT 0,
    sql_override_count    INT DEFAULT 0,
    complexity            VARCHAR(10),
    FOREIGN KEY (mapping_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
    INDEX idx_mapping_complexity (complexity)
);

CREATE TABLE transformations (
    transformation_id     VARCHAR(64) PRIMARY KEY,
    mapping_id            VARCHAR(64) NOT NULL,
    mapping_name          VARCHAR(255),
    transformation_name   VARCHAR(255),
    transformation_type   VARCHAR(100),
    reusable_flag         VARCHAR(10),
    attribute_count       INT DEFAULT 0,
    port_count            INT DEFAULT 0,
    FOREIGN KEY (mapping_id) REFERENCES mappings(mapping_id) ON DELETE CASCADE,
    INDEX idx_trans_type (transformation_type)
);

CREATE TABLE columns_metadata (
    column_id          VARCHAR(64) PRIMARY KEY,
    asset_id           VARCHAR(64) NOT NULL,
    table_name         VARCHAR(255),
    table_type         VARCHAR(20),
    column_name        VARCHAR(255),
    datatype           VARCHAR(50),
    precision_val      VARCHAR(20),
    scale_val          VARCHAR(20),
    repository_name    VARCHAR(255),
    folder_name        VARCHAR(255),
    source_file        VARCHAR(255),
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
    INDEX idx_datatype (datatype),
    INDEX idx_column_name (column_name)
);

CREATE TABLE sql_overrides (
    sql_override_id    VARCHAR(64) PRIMARY KEY,
    mapping_id         VARCHAR(64) NOT NULL,
    mapping_name       VARCHAR(255),
    context_type       VARCHAR(20),
    context_name       VARCHAR(255),
    sql_query          TEXT,
    review_status      VARCHAR(30) DEFAULT 'NOT_REVIEWED',
    FOREIGN KEY (mapping_id) REFERENCES mappings(mapping_id) ON DELETE CASCADE
);

CREATE TABLE connectors (
    connector_id        VARCHAR(64) PRIMARY KEY,
    mapping_id          VARCHAR(64) NOT NULL,
    mapping_name        VARCHAR(255),
    from_instance       VARCHAR(255),
    from_field          VARCHAR(255),
    to_instance         VARCHAR(255),
    to_field            VARCHAR(255),
    from_instance_type  VARCHAR(50),
    to_instance_type    VARCHAR(50),
    FOREIGN KEY (mapping_id) REFERENCES mappings(mapping_id) ON DELETE CASCADE
);
