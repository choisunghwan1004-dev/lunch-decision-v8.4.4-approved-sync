-- 기본 정규화 스키마입니다. 기본 DB 이름을 포함하므로 npm run setup으로 적용하는 방법을 권장합니다.
-- PK는 행 식별자, FK는 부모/참조 행 연결, UNIQUE는 업무 키의 중복 방지 규칙입니다.

-- V8.3: 새 DB에만 만드는 정규화 스키마. 기존 lunch_decision에는 어떠한 DDL/DML도 수행하지 않습니다.
CREATE DATABASE IF NOT EXISTS lunch_decision_v83 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lunch_decision_v83;

-- 국가 PK와 국가 코드·통화를 보관합니다. 한국/일본 구분의 시작점입니다.
CREATE TABLE IF NOT EXISTS countries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(8) NOT NULL,
  name VARCHAR(100) NOT NULL,
  currency CHAR(3) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE KEY uq_countries_code(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 국가 FK로 연결되는 시/도입니다. 같은 이름이라도 어느 국가인지 함께 구분합니다.
CREATE TABLE IF NOT EXISTS provinces (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  country_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(48) NOT NULL,
  name VARCHAR(150) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE KEY uq_province_country_code(country_id,code),
  UNIQUE KEY uq_province_country_name(country_id,name),
  CONSTRAINT fk_province_country FOREIGN KEY(country_id) REFERENCES countries(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 시/군/구입니다. 기존 점심·여행과 새 뉴스 주제가 함께 참조하는 실제 지역 PK입니다.
CREATE TABLE IF NOT EXISTS districts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  province_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(48) NOT NULL,
  name VARCHAR(150) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE KEY uq_district_province_code(province_id,code),
  UNIQUE KEY uq_district_province_name(province_id,name),
  CONSTRAINT fk_district_province FOREIGN KEY(province_id) REFERENCES provinces(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 행정 읍/면/동을 명확하게 분리. 일본의 하위 행정구역은 'other' 가능.
-- 행정 읍/면/동입니다. 법정동/리와 다른 개념이므로 별도 테이블로 관리합니다.
CREATE TABLE IF NOT EXISTS admin_towns (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  district_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(48) NOT NULL,
  name VARCHAR(150) NOT NULL,
  kind ENUM('eup','myeon','dong','other') NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE KEY uq_town_district_code(district_id,code),
  UNIQUE KEY uq_town_district_name(district_id,name),
  UNIQUE KEY uq_town_district_pair(district_id,id),
  CONSTRAINT fk_town_district FOREIGN KEY(district_id) REFERENCES districts(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 법정동/리: 행정동과 동일하다고 가정하지 않음.
-- 법정동/리입니다. 행정동과 연결은 다음 연결 테이블을 사용합니다.
CREATE TABLE IF NOT EXISTS legal_units (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  district_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(48) NOT NULL,
  name VARCHAR(150) NOT NULL,
  kind ENUM('legal_dong','ri','other') NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE KEY uq_legal_district_code(district_id,code),
  UNIQUE KEY uq_legal_district_name(district_id,name),
  UNIQUE KEY uq_legal_district_pair(district_id,id),
  CONSTRAINT fk_legal_district FOREIGN KEY(district_id) REFERENCES districts(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 행정동 ↔ 법정동/리의 다대다 관계. district_id 포함 복합FK로 다른 구 사이의 연결 금지.
-- 행정동 ↔ 법정동의 연결입니다. 두 PK를 조합해 같은 연결 중복을 막습니다.
CREATE TABLE IF NOT EXISTS town_legal_links (
  district_id BIGINT UNSIGNED NOT NULL,
  town_id BIGINT UNSIGNED NOT NULL,
  legal_unit_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY(town_id,legal_unit_id),
  KEY idx_tll_district(district_id),
  KEY idx_tll_legal(legal_unit_id),
  CONSTRAINT fk_tll_town_district FOREIGN KEY(district_id,town_id)
    REFERENCES admin_towns(district_id,id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_tll_legal_district FOREIGN KEY(district_id,legal_unit_id)
    REFERENCES legal_units(district_id,id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 상권은 행정동 FK와 선택 법정동 FK를 가집니다. 장소는 이 상권에 연결됩니다.
CREATE TABLE IF NOT EXISTS commercial_areas (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  town_id BIGINT UNSIGNED NOT NULL,
  legal_unit_id BIGINT UNSIGNED NULL,
  code VARCHAR(48) NOT NULL,
  name VARCHAR(150) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  is_demo BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE KEY uq_area_code(code),
  UNIQUE KEY uq_area_town_pair(town_id,id),
  KEY idx_area_town(town_id),
  KEY idx_area_legal(town_id,legal_unit_id),
  CONSTRAINT fk_area_town FOREIGN KEY(town_id) REFERENCES admin_towns(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_area_legal_link FOREIGN KEY(town_id,legal_unit_id)
    REFERENCES town_legal_links(town_id,legal_unit_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 음식점·카페·관광지·숙박을 통합 저장합니다. active와 is_demo의 의미를 구분해 사용합니다.
CREATE TABLE IF NOT EXISTS places (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  area_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(180) NOT NULL,
  place_type ENUM('restaurant','cafe','attraction','lodging') NOT NULL,
  category VARCHAR(90) NULL,
  address VARCHAR(255) NULL,
  latitude DECIMAL(10,7) NULL,
  longitude DECIMAL(10,7) NULL,
  price_min INT UNSIGNED NULL,
  price_max INT UNSIGNED NULL,
  google_place_id VARCHAR(200) NULL,
  is_demo BOOLEAN NOT NULL DEFAULT FALSE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_place_area_name_type(area_id,name,place_type),
  UNIQUE KEY uq_place_google_id(google_place_id),
  KEY idx_places_area_type(area_id,place_type),
  CONSTRAINT fk_place_area FOREIGN KEY(area_id) REFERENCES commercial_areas(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_price_range CHECK(price_max IS NULL OR price_min IS NULL OR price_max>=price_min)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 일반 회원 테이블입니다. 관리자 계정은 이 테이블이 아니라 환경 설정의 별도 계정을 사용합니다.
CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(80) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(100) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_username(username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 회원별 상권·예산·취향을 저장합니다. user_id UNIQUE로 회원당 한 설정을 유지합니다.
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  preferred_town_id BIGINT UNSIGNED NULL,
  preferred_area_id BIGINT UNSIGNED NULL,
  lunch_budget INT UNSIGNED NOT NULL DEFAULT 15000,
  group_size SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  liked_food VARCHAR(255) NULL,
  disliked_food VARCHAR(255) NULL,
  CONSTRAINT fk_preferences_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_preferences_town FOREIGN KEY(preferred_town_id) REFERENCES admin_towns(id) ON DELETE RESTRICT,
  CONSTRAINT fk_preferences_town_area FOREIGN KEY(preferred_town_id,preferred_area_id) REFERENCES commercial_areas(town_id,id) ON DELETE RESTRICT,
  CONSTRAINT ck_preferences_area_town CHECK(preferred_area_id IS NULL OR preferred_town_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 추천·방문·거절 기록입니다. 회원 FK와 장소 FK로 다음 추천에 사용할 이력을 남깁니다.
CREATE TABLE IF NOT EXISTS lunch_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  place_id BIGINT UNSIGNED NOT NULL,
  action ENUM('recommended','visited','rejected') NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_history_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_history_place FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 여행 일정 헤더 테이블입니다. 현재 자동 결정 API가 이 테이블까지 저장하지는 않습니다.
CREATE TABLE IF NOT EXISTS itineraries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  start_date DATE NOT NULL,
  days TINYINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_itinerary_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 여행의 날짜·순서별 항목을 저장할 구조입니다. 일정 FK와 장소 FK를 연결합니다.
CREATE TABLE IF NOT EXISTS itinerary_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  itinerary_id BIGINT UNSIGNED NOT NULL,
  place_id BIGINT UNSIGNED NOT NULL,
  day_no SMALLINT UNSIGNED NOT NULL,
  sequence_no SMALLINT UNSIGNED NOT NULL,
  planned_at DATETIME NULL,
  travel_minutes SMALLINT UNSIGNED NULL,
  UNIQUE KEY uq_itinerary_position(itinerary_id,day_no,sequence_no),
  CONSTRAINT fk_item_itinerary FOREIGN KEY(itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE,
  CONSTRAINT fk_item_place FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- DB 전체 경로 조회: 모든 장소는 FK를 따라 국가까지 추적할 수 있습니다.
CREATE OR REPLACE VIEW v_place_full_path AS
SELECT pl.id place_id,pl.name place_name,pl.place_type,pl.is_demo,
       a.id area_id,a.name area_name,
       t.id town_id,t.name town_name,
       lu.id legal_unit_id,lu.name legal_unit_name,lu.kind legal_unit_kind,
       d.id district_id,d.name district_name,
       p.id province_id,p.name province_name,
       c.id country_id,c.name country_name,c.code country_code
FROM places pl
JOIN commercial_areas a ON a.id=pl.area_id
JOIN admin_towns t ON t.id=a.town_id
LEFT JOIN legal_units lu ON lu.id=a.legal_unit_id
JOIN districts d ON d.id=t.district_id
JOIN provinces p ON p.id=d.province_id
JOIN countries c ON c.id=p.country_id;
