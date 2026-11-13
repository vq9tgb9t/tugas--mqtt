-- Run only against an inspected, isolated project database selected explicitly.
-- No CREATE DATABASE, DROP, ALTER, or changes to legacy tables.
CREATE TABLE IF NOT EXISTS monitoring_readings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    building VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    room VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    temperature DOUBLE NOT NULL,
    humidity DOUBLE NOT NULL,
    received_at DATETIME(6) NOT NULL COMMENT 'Server UTC',
    INDEX idx_monitoring_device_time (device_id, received_at, id),
    CHECK (temperature BETWEEN -40 AND 80),
    CHECK (humidity BETWEEN 0 AND 100)
) ENGINE=InnoDB;
