-- 뉴스 신규 테이블 정의입니다. 실제 설치는 python -m news_service.setup --init-env로 실행합니다.
-- CREATE IF NOT EXISTS는 기존 테이블의 부족한 컬럼을 추가하지 않습니다. Python 설치기의 호환 처리가 필요합니다.

-- V8.5.2 news integration, adapted from feature/v8.5.1-news-center.
-- Apply through python -m news_service.setup (includes compatibility upgrades).
-- New tables ONLY in lunch_decision_v83. Never run on lunch_decision.

-- 뉴스 주제입니다. district_id FK는 기존 지역을 재사용하고 is_demo는 운영/시연을 구분합니다.
CREATE TABLE IF NOT EXISTS news_topics(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 district_id BIGINT UNSIGNED NOT NULL,
 title VARCHAR(200) NOT NULL,
 category ENUM('festival','tourism','transport','culture','other') NOT NULL DEFAULT 'festival',
 language_code VARCHAR(12) NOT NULL DEFAULT 'ko',
 keywords VARCHAR(500),
 status ENUM('draft','ready','archived') NOT NULL DEFAULT 'draft',
 is_demo BOOLEAN NOT NULL DEFAULT FALSE,
 created_by VARCHAR(100) NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 KEY idx_news_topic_region(district_id,category,status),
 CONSTRAINT fk_news_topic_district FOREIGN KEY(district_id) REFERENCES districts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 출처 URL·기관·공개 시점·관련 구절·이용 조건입니다. URL 해시의 UNIQUE로 주제 내 중복을 막습니다.
CREATE TABLE IF NOT EXISTS news_sources(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 topic_id BIGINT UNSIGNED NOT NULL,
 source_kind ENUM('official','public_api','csv','manual','other') NOT NULL,
 organization VARCHAR(200) NOT NULL,
 source_url VARCHAR(1024),
 source_url_sha256 BINARY(32) NOT NULL,
 source_title VARCHAR(300) NOT NULL,
 source_excerpt MEDIUMTEXT,
 published_at DATETIME,
 checked_at DATETIME,
 license_note VARCHAR(500),
 content_sha256 CHAR(64),
 is_demo BOOLEAN NOT NULL DEFAULT FALSE,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_news_source_fingerprint(topic_id,source_url_sha256),
 CONSTRAINT fk_news_source_topic FOREIGN KEY(topic_id) REFERENCES news_topics(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 기사의 사실 항목입니다. 검증 상태·수치·단위·기간을 저장하고 주제 내 Fact Key를 고유하게 유지합니다.
CREATE TABLE IF NOT EXISTS news_facts(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 topic_id BIGINT UNSIGNED NOT NULL,
 fact_key VARCHAR(80) NOT NULL,
 fact_type ENUM('text','date','date_range','number','price','place','time') NOT NULL,
 value_text TEXT NOT NULL,
 value_number DECIMAL(18,4),
 unit VARCHAR(30),
 event_start DATE,
 event_end DATE,
 status ENUM('candidate','verified','rejected','disputed','outdated') NOT NULL DEFAULT 'candidate',
 verification_note TEXT,
 verified_by VARCHAR(100),
 verified_at DATETIME,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_news_fact_topic_key(topic_id,fact_key),
 CONSTRAINT fk_news_fact_topic FOREIGN KEY(topic_id) REFERENCES news_topics(id) ON DELETE RESTRICT,
 CONSTRAINT chk_news_fact_dates CHECK(event_end IS NULL OR event_start IS NULL OR event_end>=event_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Fact ↔ 출처의 다대다 연결입니다. 원문의 쪽/문단과 대조 메모도 함께 남깁니다.
CREATE TABLE IF NOT EXISTS news_fact_evidence(
 fact_id BIGINT UNSIGNED NOT NULL,
 source_id BIGINT UNSIGNED NOT NULL,
 excerpt_reference VARCHAR(500),
 evidence_note TEXT,
 checked_at DATETIME,
 PRIMARY KEY(fact_id,source_id),
 CONSTRAINT fk_nfe_fact FOREIGN KEY(fact_id) REFERENCES news_facts(id) ON DELETE RESTRICT,
 CONSTRAINT fk_nfe_source FOREIGN KEY(source_id) REFERENCES news_sources(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 기사 수정본입니다. 부모 수정본과 순번, 기사 본문, 당시 Fact 해시/JSON을 보존합니다.
CREATE TABLE IF NOT EXISTS news_drafts(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 topic_id BIGINT UNSIGNED NOT NULL,
 parent_draft_id BIGINT UNSIGNED,
 revision_no INT UNSIGNED NOT NULL,
 title VARCHAR(300) NOT NULL,
 summary_text TEXT,
 body_text LONGTEXT NOT NULL,
 model_name VARCHAR(100) NOT NULL,
 fact_snapshot_sha256 CHAR(64) NOT NULL,
 fact_snapshot_json LONGTEXT,
 status ENUM('generated','in_review','changes_requested','rejected','approved','published') NOT NULL DEFAULT 'generated',
 is_demo BOOLEAN NOT NULL DEFAULT FALSE,
 created_by VARCHAR(100) NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 approved_by VARCHAR(100),
 approved_at DATETIME,
 UNIQUE KEY uq_news_draft_revision(topic_id,revision_no),
 CONSTRAINT fk_news_draft_topic FOREIGN KEY(topic_id) REFERENCES news_topics(id) ON DELETE RESTRICT,
 CONSTRAINT fk_news_draft_parent FOREIGN KEY(parent_draft_id) REFERENCES news_drafts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 제목은 순번 0, 본문은 1부터 저장합니다. 모든 문장의 검토 상태는 기본 unverified입니다.
CREATE TABLE IF NOT EXISTS news_claims(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 draft_id BIGINT UNSIGNED NOT NULL,
 sequence_no INT UNSIGNED NOT NULL,
 statement_text TEXT NOT NULL,
 is_factual BOOLEAN NOT NULL DEFAULT TRUE,
 status ENUM('supported','unverified','contradicted','not_applicable') NOT NULL DEFAULT 'unverified',
 check_note VARCHAR(800),
 checked_at DATETIME,
 UNIQUE KEY uq_news_claim_sequence(draft_id,sequence_no),
 CONSTRAINT fk_news_claim_draft FOREIGN KEY(draft_id) REFERENCES news_drafts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 문장 ↔ Fact 연결입니다. 기사 본문에서 어느 근거를 사용했는지 추적합니다.
CREATE TABLE IF NOT EXISTS news_claim_facts(
 claim_id BIGINT UNSIGNED NOT NULL,
 fact_id BIGINT UNSIGNED NOT NULL,
 PRIMARY KEY(claim_id,fact_id),
 CONSTRAINT fk_ncf_claim FOREIGN KEY(claim_id) REFERENCES news_claims(id) ON DELETE RESTRICT,
 CONSTRAINT fk_ncf_fact FOREIGN KEY(fact_id) REFERENCES news_facts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 요청·수정·반려·승인·게시·중단 이력입니다. 승인에는 내용/근거 해시를 함께 저장합니다.
CREATE TABLE IF NOT EXISTS news_reviews(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 draft_id BIGINT UNSIGNED NOT NULL,
 action ENUM('submitted','changes_requested','rejected','approved','published','unpublished') NOT NULL,
 reviewer_key VARCHAR(100) NOT NULL,
 reason TEXT,
 fact_snapshot_sha256 CHAR(64),
 content_sha256 CHAR(64),
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_news_review_draft FOREIGN KEY(draft_id) REFERENCES news_drafts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 게시된 수정본과 공개 URL 식별자입니다. 기사 행을 삭제하지 않고 상태와 중단 사유를 남깁니다.
CREATE TABLE IF NOT EXISTS news_publications(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 topic_id BIGINT UNSIGNED NOT NULL,
 draft_id BIGINT UNSIGNED NOT NULL,
 slug VARCHAR(200) NOT NULL,
 status ENUM('published','unpublished') NOT NULL DEFAULT 'published',
 published_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 unpublished_at DATETIME,
 retraction_reason TEXT,
 UNIQUE KEY uq_news_publication_slug(slug),
 UNIQUE KEY uq_news_publication_draft(draft_id),
 CONSTRAINT fk_news_pub_topic FOREIGN KEY(topic_id) REFERENCES news_topics(id) ON DELETE RESTRICT,
 CONSTRAINT fk_news_pub_draft FOREIGN KEY(draft_id) REFERENCES news_drafts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- AI 모델·요청 ID·토큰·성공/실패 기록입니다. 비용 컬럼은 현재 자동 계산하지 않습니다.
CREATE TABLE IF NOT EXISTS news_ai_usage(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 topic_id BIGINT UNSIGNED NOT NULL,
 draft_id BIGINT UNSIGNED,
 model_name VARCHAR(100) NOT NULL,
 provider_request_id VARCHAR(150),
 input_tokens INT UNSIGNED NOT NULL DEFAULT 0,
 output_tokens INT UNSIGNED NOT NULL DEFAULT 0,
 cached_input_tokens INT UNSIGNED NOT NULL DEFAULT 0,
 cost_usd DECIMAL(12,6),
 status ENUM('success','error') NOT NULL,
 error_code VARCHAR(100),
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_news_usage_topic FOREIGN KEY(topic_id) REFERENCES news_topics(id) ON DELETE RESTRICT,
 CONSTRAINT fk_news_usage_draft FOREIGN KEY(draft_id) REFERENCES news_drafts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Python 설치기가 모든 보정을 마친 뒤 버전을 기록합니다. SQL만 실행해서는 버전 행이 생기지 않습니다.
CREATE TABLE IF NOT EXISTS news_schema_version(
 name VARCHAR(40) PRIMARY KEY, version VARCHAR(20) NOT NULL,
 applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
