-- 실행은 npm run setup을 사용하세요. 이 SQL은 신규 DB 확장의 참고 정의이며 재실행 시 중복 오류가 납니다.
-- 신규 V8.3 DB에만 적용. 기존 lunch_decision은 변경하지 않음.
USE lunch_decision_v83;
ALTER TABLE places
  ADD COLUMN main_menu VARCHAR(200) NULL,
  ADD COLUMN description VARCHAR(500) NULL,
  ADD COLUMN phone VARCHAR(80) NULL,
  ADD COLUMN image_path VARCHAR(500) NULL,
  ADD COLUMN rating DECIMAL(3,1) NULL,
  ADD COLUMN review_count INT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN lunch_start TIME NULL,
  ADD COLUMN lunch_end TIME NULL,
  ADD COLUMN open_days VARCHAR(30) NULL;
ALTER TABLE user_preferences
  ADD COLUMN latitude DECIMAL(10,7) NULL,
  ADD COLUMN longitude DECIMAL(10,7) NULL;
ALTER TABLE lunch_history
  ADD COLUMN reject_reason VARCHAR(200) NULL,
  ADD COLUMN memo VARCHAR(500) NULL,
  ADD COLUMN visit_date DATE NULL,
  ADD COLUMN decision_score DECIMAL(8,2) NULL;
ALTER TABLE lunch_history MODIFY action ENUM('recommended','visited','rejected','accepted') NOT NULL;
CREATE TABLE IF NOT EXISTS migration_mappings (
  legacy_table VARCHAR(60) NOT NULL,
  legacy_id BIGINT UNSIGNED NOT NULL,
  new_table VARCHAR(60) NOT NULL,
  new_id BIGINT UNSIGNED NOT NULL,
  migrated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(legacy_table,legacy_id),
  INDEX idx_new_reference(new_table,new_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
