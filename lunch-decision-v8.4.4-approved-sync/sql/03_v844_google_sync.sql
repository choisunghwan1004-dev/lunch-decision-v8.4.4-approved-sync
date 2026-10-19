-- Google 승인 기록 테이블입니다. 먼저 기본 스키마를 준비하고 npm run setup:sync으로 적용합니다.

-- One-time migration ONLY for V8.3 database. Do not execute against OLD_DB_NAME.
-- 장소 활성화 전에 사람이 확인한 지역·상권과 검토 시점을 기록합니다. 뉴스 승인과는 별개입니다.
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
