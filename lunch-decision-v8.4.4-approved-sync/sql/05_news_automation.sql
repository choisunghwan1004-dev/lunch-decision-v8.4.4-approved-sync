-- 선택 설치: 매일 16:00 예약 실행과 노션 전송 상태입니다. 04 뉴스 스키마 설치 후 적용합니다.
-- 날짜는 한국 시간 기준입니다. 같은 날 같은 주제의 OpenAI 중복 호출을 차단합니다.
CREATE TABLE IF NOT EXISTS news_automation_runs (
  run_date DATE NOT NULL,
  topic_id BIGINT UNSIGNED NOT NULL,
  draft_id BIGINT UNSIGNED NULL,
  status VARCHAR(30) NOT NULL,
  source_page_id VARCHAR(36) NULL,
  notion_page_id VARCHAR(36) NULL,
  error_code VARCHAR(100) NULL,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(run_date, topic_id),
  CONSTRAINT fk_auto_topic FOREIGN KEY(topic_id) REFERENCES news_topics(id),
  CONSTRAINT fk_auto_draft FOREIGN KEY(draft_id) REFERENCES news_drafts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
