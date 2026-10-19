-- One-time migration ONLY for V8.3 database. Do not execute against OLD_DB_NAME.
CREATE TABLE IF NOT EXISTS google_sync_reviews (
  place_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  area_id BIGINT UNSIGNED NOT NULL,
  reviewed_by VARCHAR(80) NOT NULL,
  address_region_verified BOOLEAN NOT NULL DEFAULT TRUE,
  town_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  town_address_matched BOOLEAN NOT NULL DEFAULT FALSE,
  commercial_area_confirmed BOOLEAN NOT NULL DEFAULT TRUE,
  approved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  activated_at DATETIME NULL,
  CONSTRAINT fk_gsr_place FOREIGN KEY (place_id) REFERENCES places(id) ON DELETE RESTRICT,
  CONSTRAINT fk_gsr_area FOREIGN KEY (area_id) REFERENCES commercial_areas(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
