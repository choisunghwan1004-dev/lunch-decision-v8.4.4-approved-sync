-- TEST FIXTURE ONLY: predecessor schema from feature/v8.5.1-news-center; not an installation script.
-- V8.5.1 regional news (run ONCE via npm run news:setup).
-- New tables ONLY in lunch_decision_v83. Never run on lunch_decision.
USE lunch_decision_v83;
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
CREATE TABLE IF NOT EXISTS news_sources(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 topic_id BIGINT UNSIGNED NOT NULL,
 source_kind ENUM('official','public_api','csv','manual','other') NOT NULL,
 organization VARCHAR(200) NOT NULL,
 source_url VARCHAR(1024),
 source_url_sha256 BINARY(32) NOT NULL,
 source_title VARCHAR(300) NOT NULL,
 published_at DATETIME,
 checked_at DATETIME,
 license_note VARCHAR(500),
 content_sha256 CHAR(64),
 is_demo BOOLEAN NOT NULL DEFAULT FALSE,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_news_source_fingerprint(topic_id,source_url_sha256),
 CONSTRAINT fk_news_source_topic FOREIGN KEY(topic_id) REFERENCES news_topics(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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
CREATE TABLE IF NOT EXISTS news_claim_facts(
 claim_id BIGINT UNSIGNED NOT NULL,
 fact_id BIGINT UNSIGNED NOT NULL,
 PRIMARY KEY(claim_id,fact_id),
 CONSTRAINT fk_ncf_claim FOREIGN KEY(claim_id) REFERENCES news_claims(id) ON DELETE RESTRICT,
 CONSTRAINT fk_ncf_fact FOREIGN KEY(fact_id) REFERENCES news_facts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS news_reviews(
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 draft_id BIGINT UNSIGNED NOT NULL,
 action ENUM('submitted','changes_requested','rejected','approved','published','unpublished') NOT NULL,
 reviewer_key VARCHAR(100) NOT NULL,
 reason TEXT,
 fact_snapshot_sha256 CHAR(64),
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_news_review_draft FOREIGN KEY(draft_id) REFERENCES news_drafts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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

