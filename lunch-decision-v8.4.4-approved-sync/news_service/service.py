# 뉴스 업무의 중심: 출처 → Fact 검증 → 초안 → 문장 대조 → 최종 승인 → 게시를 처리합니다.
# tx는 현재 트랜잭션의 SQL 실행 도구이며 %s 자리에 값을 별도로 전달합니다.
# 쓰기 작업은 먼저 주제 행을 잠가 같은 주제의 승인·수정·게시가 엇갈리지 않게 합니다.
# 읽는 핵심: sheet → generate → save_article → check_claim → review → publish → public.

"""Transactional newsroom workflow; approval binds both content and evidence."""
import hashlib
import json

from . import article_ai
from .db import Database
from .validation import can_verify, complete_evidence, content_hash, fingerprint, parse_draft, snapshot, validate_source


# 처리할 수 없는 업무 상태를 예외로 전달합니다. 앱은 이를 상태 코드와 한글 안내로 변환합니다.
class NewsError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status


# 필수 행이나 목록이 없으면 즉시 중단하는 공통 검사입니다.
def need(value, message, status=404):
    if not value:
        raise NewsError(message, status)
    return value


# HTTP나 화면과 분리된 뉴스 업무 객체입니다. DB와 AI 생성기를 교체할 수 있어 독립 테스트가 가능합니다.
class NewsService:
    def __init__(self, database=None, generator=None):
        self.db = database or Database()
        self.generator = generator or article_ai.generate_article

    # 주제를 읽고 지역명을 붙입니다. lock=True면 다른 쓰기 작업이 끝날 때까지 같은 주제를 기다립니다.
    def topic(self, tx, topic_id, lock=False):
        # Always lock the topic before locking or changing subordinate rows.
        row = tx.one('SELECT * FROM news_topics WHERE id=%s' + (' FOR UPDATE' if lock else ''), (topic_id,))
        need(row, '주제를 찾지 못했습니다.')
        region = tx.one('SELECT d.name district_name,p.name province_name FROM districts d JOIN provinces p ON p.id=d.province_id WHERE d.id=%s', (row['district_id'],))
        row['region_name'] = region['province_name'] + ' / ' + region['district_name']
        return row

    # 초안·문장·Fact Key를 묶고 현재 내용의 해시를 계산합니다. 쓰기는 주제부터 잠급니다.
    def draft(self, tx, draft_id, lock=False):
        row = tx.one('SELECT * FROM news_drafts WHERE id=%s', (draft_id,))
        need(row, '초안을 찾지 못했습니다.')
        topic = self.topic(tx, row['topic_id'], lock)
        if lock:
            row = tx.one('SELECT * FROM news_drafts WHERE id=%s FOR UPDATE', (draft_id,))
        claims = tx.all('SELECT * FROM news_claims WHERE draft_id=%s ORDER BY sequence_no', (draft_id,))
        for claim in claims:
            claim['fact_keys'] = [r['fact_key'] for r in tx.all('SELECT f.fact_key FROM news_claim_facts c JOIN news_facts f ON f.id=c.fact_id WHERE c.claim_id=%s ORDER BY f.fact_key', (claim['id'],))]
        row['claims'] = claims
        row['content_hash'] = content_hash(row, claims)
        row['region_name'] = topic['region_name']
        return row, topic

    # verified이며 모든 출처가 완전한 Fact만 모읍니다. 주제·값·출처까지 묶어 근거 해시를 만듭니다.
    def sheet(self, tx, topic):
        facts = tx.all("SELECT * FROM news_facts WHERE topic_id=%s AND status='verified' ORDER BY fact_key", (topic['id'],))
        complete = []
        for fact in facts:
            fact['evidence'] = tx.all('''SELECT e.source_id,e.excerpt_reference,e.evidence_note,e.checked_at,
                s.source_kind,s.organization,s.source_url,s.source_title,s.published_at,s.source_excerpt,
                s.license_note,s.content_sha256,s.is_demo
                FROM news_fact_evidence e JOIN news_sources s ON s.id=e.source_id
                WHERE e.fact_id=%s AND s.topic_id=%s ORDER BY s.id''', (fact['id'], topic['id']))
            if fact['evidence'] and all(complete_evidence(e) for e in fact['evidence']):
                complete.append(fact)
        context = {key: topic[key] for key in ('id', 'district_id', 'title', 'category', 'language_code', 'is_demo')}
        digest = fingerprint({'topic': context, 'facts': snapshot(complete)})
        return complete, digest

    # 누가 어떤 버전을 어떤 사유로 처리했는지 남깁니다. 승인에는 기사·근거 해시도 묶습니다.
    def review_log(self, tx, draft_id, action, editor, reason, fact_hash=None, article_hash=None):
        tx.insert('''INSERT INTO news_reviews(draft_id,action,reviewer_key,reason,fact_snapshot_sha256,content_sha256)
                     VALUES(%s,%s,%s,%s,%s,%s)''', (draft_id, action, editor, reason, fact_hash, article_hash))

    # 근거가 바뀌면 같은 주제의 검토·승인을 해제하고 게시를 중단합니다. 과거 기사 원문은 삭제하지 않습니다.
    def invalidate(self, tx, topic_id, editor, reason):
        affected = tx.all("SELECT id FROM news_drafts WHERE topic_id=%s AND status NOT IN ('rejected','changes_requested')", (topic_id,))
        for draft in affected:
            self.review_log(tx, draft['id'], 'changes_requested', editor, reason)
        live = tx.all("SELECT draft_id FROM news_publications WHERE topic_id=%s AND status='published'", (topic_id,))
        for row in live:
            self.review_log(tx, row['draft_id'], 'unpublished', editor, reason)
        tx.execute("UPDATE news_publications SET status='unpublished',unpublished_at=NOW(),retraction_reason=%s WHERE topic_id=%s AND status='published'", (reason, topic_id))
        tx.execute("UPDATE news_drafts SET status='changes_requested',approved_by=NULL,approved_at=NULL WHERE topic_id=%s AND status NOT IN ('rejected','changes_requested')", (topic_id,))
        tx.execute("UPDATE news_claims SET status='unverified',check_note=NULL,checked_at=NULL WHERE draft_id IN (SELECT id FROM news_drafts WHERE topic_id=%s)", (topic_id,))

    # 기존 시군구 목록을 읽습니다. 한국·일본 모두 동일한 districts PK를 사용합니다.
    def regions(self):
        with self.db.transaction() as tx:
            rows = tx.all('SELECT d.id,d.name district_name,p.name province_name FROM districts d JOIN provinces p ON p.id=d.province_id ORDER BY p.name,d.name')
            return [{'id': r['id'], 'label': r['province_name'] + ' / ' + r['district_name']} for r in rows]

    # 최근 주제 목록과 검증 Fact 수·초안 수를 반환하여 관리자 목록을 구성합니다.
    def topics(self):
        with self.db.transaction() as tx:
            rows = tx.all('''SELECT t.*,d.name district_name,p.name province_name,
                (SELECT COUNT(*) FROM news_facts f WHERE f.topic_id=t.id AND f.status='verified') verified_count,
                (SELECT COUNT(*) FROM news_drafts a WHERE a.topic_id=t.id) draft_count
                FROM news_topics t JOIN districts d ON d.id=t.district_id JOIN provinces p ON p.id=d.province_id
                ORDER BY t.id DESC LIMIT 100''')
            for row in rows:
                row['region_name'] = row.pop('province_name') + ' / ' + row.pop('district_name')
            return rows

    # 존재하는 시군구인지 확인한 뒤 주제를 만듭니다. 화면의 가상 지역 ID를 넣으면 안 됩니다.
    def create_topic(self, data, editor):
        with self.db.transaction() as tx:
            need(tx.one('SELECT id FROM districts WHERE id=%s', (data['district_id'],)), '등록된 시군구를 선택하세요.', 422)
            ident = tx.insert("INSERT INTO news_topics(district_id,title,category,status,is_demo,created_by) VALUES(%s,%s,%s,'draft',%s,%s)",
                              (data['district_id'], data['title'], data['category'], data['is_demo'], editor))
            return {'ok': True, 'id': ident}

    # 현재 주제의 원자료와 사람의 대조에 필요한 필드를 조회합니다.
    def sources(self, topic_id):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id)
            return tx.all('SELECT id,topic_id,source_kind,organization,source_title,source_url,published_at,checked_at,source_excerpt,license_note,is_demo FROM news_sources WHERE topic_id=%s ORDER BY id', (topic_id,))

    # 같은 URL의 중복을 막습니다. 기존 출처를 수정하면 연결 Fact를 후보로 되돌리고 기사도 재검토시킵니다.
    def save_source(self, topic_id, data, editor, source_id=None):
        validate_source(data)
        with self.db.transaction() as tx:
            topic = self.topic(tx, topic_id, True)
            duplicate = tx.one('SELECT id FROM news_sources WHERE topic_id=%s AND source_url_sha256=UNHEX(%s)', (topic_id, hashlib.sha256(data['source_url'].encode()).hexdigest()))
            if duplicate and duplicate['id'] != source_id:
                raise NewsError('이 URL은 이미 등록되어 있습니다.')
            values = (data['source_kind'], data['organization'], data['source_title'], data['source_url'],
                      hashlib.sha256(data['source_url'].encode()).hexdigest(), data['published_at'],
                      data['source_excerpt'], data['license_note'], hashlib.sha256(data['source_excerpt'].encode()).hexdigest())
            if source_id:
                need(tx.one('SELECT id FROM news_sources WHERE id=%s AND topic_id=%s', (source_id, topic_id)), '출처가 없습니다.')
                self.invalidate(tx, topic_id, editor, '출처 원자료가 수정되어 재검토가 필요합니다.')
                tx.execute("UPDATE news_facts SET status='candidate',verified_by=NULL,verified_at=NULL WHERE id IN (SELECT fact_id FROM news_fact_evidence WHERE source_id=%s)", (source_id,))
                tx.execute('''UPDATE news_sources SET source_kind=%s,organization=%s,source_title=%s,source_url=%s,
                    source_url_sha256=UNHEX(%s),published_at=%s,source_excerpt=%s,license_note=%s,content_sha256=%s,checked_at=NOW()
                    WHERE id=%s AND topic_id=%s''', (*values, source_id, topic_id))
                ident = source_id
            else:
                ident = tx.insert('''INSERT INTO news_sources(source_kind,organization,source_title,source_url,source_url_sha256,
                    published_at,source_excerpt,license_note,content_sha256,topic_id,is_demo,checked_at)
                    VALUES(%s,%s,%s,%s,UNHEX(%s),%s,%s,%s,%s,%s,%s,NOW())''', (*values, topic_id, topic['is_demo']))
            return {'ok': True, 'id': ident}

    # Fact가 사용하는 출처는 삭제하지 않습니다. 먼저 근거 연결을 해제해야 합니다.
    def delete_source(self, topic_id, source_id, editor):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id, True)
            need(tx.one('SELECT id FROM news_sources WHERE id=%s AND topic_id=%s', (source_id, topic_id)), '출처가 없습니다.')
            if tx.one('SELECT fact_id FROM news_fact_evidence WHERE source_id=%s LIMIT 1', (source_id,)):
                raise NewsError('Fact가 참조 중인 출처입니다. 연결을 먼저 해제하세요.')
            tx.execute('DELETE FROM news_sources WHERE id=%s AND topic_id=%s', (source_id, topic_id))
            return {'ok': True}

    # 후보·검증·만료 등 모든 Fact와 연결 출처를 읽어 관리자가 상태를 비교할 수 있게 합니다.
    def facts(self, topic_id):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id)
            rows = tx.all('SELECT * FROM news_facts WHERE topic_id=%s ORDER BY fact_key', (topic_id,))
            for row in rows:
                row['evidence'] = tx.all('SELECT e.*,s.source_title,s.source_url,s.organization,s.source_excerpt,s.published_at,s.license_note FROM news_fact_evidence e JOIN news_sources s ON s.id=e.source_id WHERE e.fact_id=%s ORDER BY e.source_id', (row['id'],))
            return rows

    # 새 Fact는 candidate입니다. 값을 수정하면 기존 검증·승인을 그대로 이어 쓰지 않습니다.
    def save_fact(self, topic_id, data, editor, fact_id=None):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id, True)
            existing = tx.one('SELECT id FROM news_facts WHERE topic_id=%s AND fact_key=%s', (topic_id, data['fact_key']))
            if existing and existing['id'] != fact_id:
                raise NewsError('이 주제에 같은 Fact Key가 있습니다.')
            values = tuple(data.get(key) for key in ('fact_key', 'fact_type', 'value_text', 'value_number', 'unit', 'event_start', 'event_end'))
            if fact_id:
                need(tx.one('SELECT id FROM news_facts WHERE id=%s AND topic_id=%s', (fact_id, topic_id)), 'Fact가 없습니다.')
                self.invalidate(tx, topic_id, editor, 'Fact 내용이 변경되어 재검토가 필요합니다.')
                tx.execute("UPDATE news_facts SET fact_key=%s,fact_type=%s,value_text=%s,value_number=%s,unit=%s,event_start=%s,event_end=%s,status='candidate',verification_note=NULL,verified_by=NULL,verified_at=NULL WHERE id=%s AND topic_id=%s", (*values, fact_id, topic_id))
                ident = fact_id
            else:
                ident = tx.insert("INSERT INTO news_facts(fact_key,fact_type,value_text,value_number,unit,event_start,event_end,topic_id,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'candidate')", (*values, topic_id))
            return {'ok': True, 'id': ident, 'status': 'candidate'}

    # 소속 주제부터 확인합니다. 이미 기사에 쓰인 Fact는 이력 보존을 위해 삭제 대신 상태를 바꿉니다.
    def delete_fact(self, topic_id, fact_id, editor):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id, True)
            # Ownership checked BEFORE deleting any subordinate evidence.
            need(tx.one('SELECT id FROM news_facts WHERE id=%s AND topic_id=%s', (fact_id, topic_id)), 'Fact가 없습니다.')
            if tx.one('SELECT claim_id FROM news_claim_facts WHERE fact_id=%s LIMIT 1', (fact_id,)):
                raise NewsError('기사 이력에서 참조한 Fact는 삭제할 수 없습니다. 상태를 변경하세요.')
            self.invalidate(tx, topic_id, editor, 'Fact가 삭제되어 재검토가 필요합니다.')
            tx.execute('DELETE FROM news_fact_evidence WHERE fact_id=%s', (fact_id,))
            tx.execute('DELETE FROM news_facts WHERE id=%s AND topic_id=%s', (fact_id, topic_id))
            return {'ok': True}

    # Fact와 출처가 같은 주제인지 검사한 뒤 연결을 저장/해제합니다. 연결 변경도 재검증 대상입니다.
    def evidence(self, topic_id, fact_id, data, editor, delete=False):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id, True)
            need(tx.one('SELECT id FROM news_facts WHERE id=%s AND topic_id=%s', (fact_id, topic_id)), 'Fact가 없습니다.')
            need(tx.one('SELECT id FROM news_sources WHERE id=%s AND topic_id=%s', (data['source_id'], topic_id)), '같은 주제의 출처를 선택하세요.', 422)
            self.invalidate(tx, topic_id, editor, 'Fact 근거 연결이 변경되어 재검토가 필요합니다.')
            tx.execute('DELETE FROM news_fact_evidence WHERE fact_id=%s AND source_id=%s', (fact_id, data['source_id']))
            if not delete:
                tx.execute('INSERT INTO news_fact_evidence(fact_id,source_id,excerpt_reference,evidence_note,checked_at) VALUES(%s,%s,%s,%s,NOW())', (fact_id, data['source_id'], data['excerpt_reference'], data['evidence_note']))
            tx.execute("UPDATE news_facts SET status='candidate',verified_by=NULL,verified_at=NULL WHERE id=%s", (fact_id,))
            return {'ok': True, 'status': 'candidate'}

    # 사람의 원문 대조를 저장합니다. 연결된 모든 출처가 완전해야 verified로 바꿉니다.
    def verify_fact(self, topic_id, fact_id, data, editor):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id, True)
            fact = need(tx.one('SELECT * FROM news_facts WHERE id=%s AND topic_id=%s', (fact_id, topic_id)), 'Fact가 없습니다.')
            evidence = tx.all('SELECT s.* FROM news_fact_evidence e JOIN news_sources s ON s.id=e.source_id WHERE e.fact_id=%s AND s.topic_id=%s', (fact_id, topic_id))
            if evidence and not all(complete_evidence(e) for e in evidence):
                raise NewsError('연결된 모든 출처의 HTTPS URL·공개 시점·원자료 구절·이용 조건을 먼저 채우세요.', 422)
            can_verify(fact, len(evidence), data['editor_confirmed'], data['verification_note'])
            self.invalidate(tx, topic_id, editor, 'Fact 검증 상태가 변경되어 재검토가 필요합니다.')
            tx.execute("UPDATE news_facts SET status='verified',verification_note=%s,verified_by=%s,verified_at=NOW() WHERE id=%s", (data['verification_note'], editor, fact_id))
            return {'ok': True, 'status': 'verified'}

    # Fact를 이견·만료 등으로 바꾸고 그 근거를 쓰는 게시 기사도 중단합니다.
    def fact_status(self, topic_id, fact_id, data, editor):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id, True)
            need(tx.one('SELECT id FROM news_facts WHERE id=%s AND topic_id=%s', (fact_id, topic_id)), 'Fact가 없습니다.')
            self.invalidate(tx, topic_id, editor, data['reason'])
            tx.execute('UPDATE news_facts SET status=%s,verification_note=%s,verified_by=NULL,verified_at=NULL WHERE id=%s', (data['status'], data['reason'], fact_id))
            return {'ok': True, 'status': data['status']}

    # 관리자에게 검증 Fact 목록과 현재 근거 해시를 함께 돌려줍니다.
    def fact_sheet(self, topic_id):
        with self.db.transaction() as tx:
            topic = self.topic(tx, topic_id)
            facts, digest = self.sheet(tx, topic)
            return {'topic': topic, 'facts': facts, 'snapshot_hash': digest}

    # 주제 내 수정 번호를 발급하고 기사·당시 근거 JSON·제목/본문 문장·Fact 연결을 한 트랜잭션에 저장합니다.
    def save_article(self, tx, topic, article, digest, editor, model, parent=None):
        revision = tx.one('SELECT COALESCE(MAX(revision_no),0)+1 n FROM news_drafts WHERE topic_id=%s', (topic['id'],))['n']
        facts, actual_digest = self.sheet(tx, topic)
        if actual_digest != digest:
            raise NewsError('저장 시점의 Fact Sheet가 달라졌습니다. 다시 확인하세요.')
        saved_sheet = json.dumps({'region_name': topic['region_name'], 'topic_title': topic['title'],
                                 'facts': snapshot(facts)}, ensure_ascii=False, sort_keys=True, default=str)
        ident = tx.insert("INSERT INTO news_drafts(topic_id,parent_draft_id,revision_no,title,summary_text,body_text,model_name,fact_snapshot_sha256,fact_snapshot_json,status,is_demo,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'generated',%s,%s)",
                          (topic['id'], parent, revision, article['title'], article['claims'][0]['sentence'], article['body'], model, digest, saved_sheet, topic['is_demo'], editor))
        keys = {r['fact_key']: r['id'] for r in tx.all("SELECT id,fact_key FROM news_facts WHERE topic_id=%s AND status='verified'", (topic['id'],))}
        for sequence, claim in enumerate([{'sentence': article['title'], 'fact_keys': article['title_fact_keys']}, *article['claims']]):
            claim_id = tx.insert("INSERT INTO news_claims(draft_id,sequence_no,statement_text,is_factual,status) VALUES(%s,%s,%s,1,'unverified')", (ident, sequence, claim['sentence']))
            for key in claim['fact_keys']:
                tx.execute('INSERT INTO news_claim_facts(claim_id,fact_id) VALUES(%s,%s)', (claim_id, keys[key]))
        return {'ok': True, 'id': ident, 'revision_no': revision, 'status': 'generated'}

    # DB에서 검증 근거를 읽은 뒤 연결을 닫고 AI를 호출합니다. 응답 후 다시 잠가 근거 변경을 확인합니다.
    def generate(self, topic_id, editor):
        with self.db.transaction() as tx:
            topic = self.topic(tx, topic_id)
            facts, digest = self.sheet(tx, topic)
            need(facts, '검증 완료된 Fact와 원자료 연결이 필요합니다.', 422)
            if len(facts) > 40 or len(json.dumps(snapshot(facts), ensure_ascii=False, default=str)) > 60000:
                raise NewsError('한 주제의 검증 자료를 40개·60,000자 이내로 정리하세요.', 422)
        # Do not hold DB locks while waiting for the provider.
        try:
            article, usage = self.generator(topic, facts)
            article = parse_draft({k: article[k] for k in ('title', 'title_fact_keys', 'claims')}, {f['fact_key'] for f in facts})
        except Exception as error:
            with self.db.transaction() as tx:
                self.topic(tx, topic_id, True)
                code = error.code if isinstance(error, article_ai.NewsAIError) else type(error).__name__[:100]
                tx.execute("INSERT INTO news_ai_usage(topic_id,model_name,status,error_code) VALUES(%s,%s,'error',%s)", (topic_id, article_ai.MODEL, code))
            if isinstance(error, article_ai.NewsAIError):
                raise
            if isinstance(error, ValueError):
                raise NewsError(str(error), 422) from error
            raise NewsError('AI 초안 생성에 실패했습니다. 키·모델 권한·한도를 확인하세요. 자동 재시도하지 않았습니다.', 502) from error
        with self.db.transaction() as tx:
            current = self.topic(tx, topic_id, True)
            _, current_digest = self.sheet(tx, current)
            if current_digest != digest:
                tx.execute("INSERT INTO news_ai_usage(topic_id,model_name,provider_request_id,input_tokens,output_tokens,cached_input_tokens,status,error_code) VALUES(%s,%s,%s,%s,%s,%s,'error','EvidenceChanged')", (topic_id, article_ai.MODEL, usage.get('request_id'), usage.get('input_tokens', 0), usage.get('output_tokens', 0), usage.get('cached_input_tokens', 0)))
                # Commit usage even though the draft is discarded.
                result = None
            else:
                result = self.save_article(tx, current, article, digest, editor, article_ai.MODEL)
                tx.execute("INSERT INTO news_ai_usage(topic_id,draft_id,model_name,provider_request_id,input_tokens,output_tokens,cached_input_tokens,status) VALUES(%s,%s,%s,%s,%s,%s,%s,'success')", (topic_id, result['id'], article_ai.MODEL, usage.get('request_id'), usage.get('input_tokens', 0), usage.get('output_tokens', 0), usage.get('cached_input_tokens', 0)))
        if result is None:
            raise NewsError('생성 중 근거가 바뀌어 초안을 폐기했습니다. Fact Sheet 확인 후 다시 생성하세요.')
        return result

    # 같은 주제의 수정본들을 최신 수정 번호 순으로 보여줍니다.
    def drafts(self, topic_id):
        with self.db.transaction() as tx:
            self.topic(tx, topic_id)
            return tx.all('SELECT id,topic_id,parent_draft_id,revision_no,title,model_name,status,is_demo,created_by,created_at,approved_by,approved_at FROM news_drafts WHERE topic_id=%s ORDER BY revision_no DESC', (topic_id,))

    # 현재 검증 자료와 수정본 저장 당시 자료를 함께 반환합니다. 근거가 바뀌었는지도 표시합니다.
    def detail(self, draft_id):
        with self.db.transaction() as tx:
            draft, topic = self.draft(tx, draft_id)
            facts, digest = self.sheet(tx, topic)
            draft['evidence_current'] = digest == draft['fact_snapshot_sha256']
            draft['facts'] = facts
            saved_sheet = draft.pop('fact_snapshot_json', None)
            draft['saved_fact_sheet'] = json.loads(saved_sheet) if saved_sheet else None
            draft['reviews'] = tx.all('SELECT * FROM news_reviews WHERE draft_id=%s ORDER BY id', (draft_id,))
            draft['publication'] = tx.one('SELECT id,status,published_at,unpublished_at,retraction_reason FROM news_publications WHERE draft_id=%s', (draft_id,))
            return draft

    # 사용자가 열어 본 내용 해시와 현재 기사 해시가 다르면 오래된 화면의 요청을 거절합니다.
    def expected(self, draft, value):
        if draft['content_hash'] != value:
            raise NewsError('기사 버전이 바뀌었습니다. 다시 열어 확인하세요.')

    # 기존 본문을 덮어쓰지 않고 부모 초안을 연결한 새 수정본을 만듭니다. 모든 문장은 다시 미검토입니다.
    def edit(self, draft_id, data, editor):
        with self.db.transaction() as tx:
            draft, topic = self.draft(tx, draft_id, True)
            self.expected(draft, data['expected_content_hash'])
            facts, digest = self.sheet(tx, topic)
            article = parse_draft({k: data[k] for k in ('title', 'title_fact_keys', 'claims')}, {f['fact_key'] for f in facts})
            result = self.save_article(tx, topic, article, digest, editor, draft['model_name'], draft_id)
            self.review_log(tx, result['id'], 'submitted', editor, '새 수정본 저장: ' + data['reason'], digest)
            return result

    # 사람이 문장 하나를 대조한 결과를 저장합니다. 승인·게시된 기사는 새 수정본으로 검토해야 합니다.
    def check_claim(self, draft_id, claim_id, data, editor):
        with self.db.transaction() as tx:
            draft, topic = self.draft(tx, draft_id, True)
            self.expected(draft, data['expected_content_hash'])
            if draft['status'] not in ('generated', 'in_review', 'changes_requested'):
                raise NewsError('승인·게시된 기사와 반려 기사는 새 수정본을 만들어 검토하세요.')
            _, digest = self.sheet(tx, topic)
            if digest != draft['fact_snapshot_sha256']:
                raise NewsError('Fact Sheet가 바뀌었습니다. 현재 근거로 새 수정본을 저장하세요.')
            claim = need(next((c for c in draft['claims'] if c['id'] == claim_id), None), '문장이 없습니다.')
            need(claim['fact_keys'], '문장에 Fact 연결이 필요합니다.', 422)
            tx.execute('UPDATE news_claims SET status=%s,check_note=%s,checked_at=NOW() WHERE id=%s AND draft_id=%s', (data['status'], editor + ': ' + data['note'][:680], claim_id, draft_id))
            tx.execute("UPDATE news_drafts SET status='in_review',approved_by=NULL,approved_at=NULL WHERE id=%s", (draft_id,))
            self.review_log(tx, draft_id, 'submitted', editor, '문장 ' + str(claim['sequence_no']) + ' ' + data['status'] + ': ' + data['note'], digest, draft['content_hash'])
            return {'ok': True, 'status': data['status']}

    # 시연 여부·현재 근거·모든 문장 판정·제목/본문 대응을 검사하는 승인/게시 공통 관문입니다.
    def approvable(self, tx, draft, topic):
        facts, digest = self.sheet(tx, topic)
        if draft['is_demo'] or topic['is_demo']:
            raise NewsError('가상·시연 자료는 운영 게시할 수 없습니다.')
        if any(e['is_demo'] for f in facts for e in f['evidence']):
            raise NewsError('시연용 출처가 포함된 Fact는 운영 게시할 수 없습니다.')
        if digest != draft['fact_snapshot_sha256']:
            raise NewsError('근거가 변경되어 재작성·재검토가 필요합니다.')
        if not draft['claims'] or any(c['status'] != 'supported' or not c['fact_keys'] for c in draft['claims']):
            raise NewsError('제목과 모든 본문 문장의 원자료 대조를 완료하세요.')
        if draft['claims'][0]['sequence_no'] != 0 or draft['claims'][0]['statement_text'] != draft['title'] or '\n\n'.join(c['statement_text'] for c in draft['claims'][1:]) != draft['body_text']:
            raise NewsError('기사 본문과 문장별 근거가 일치하지 않습니다.')
        return digest

    # 최종 승인에는 검토 중 상태와 4개 확인이 필요합니다. 승인 당시 기사·근거 지문을 이력에 남깁니다.
    def review(self, draft_id, data, editor):
        with self.db.transaction() as tx:
            draft, topic = self.draft(tx, draft_id, True)
            self.expected(draft, data['expected_content_hash'])
            action = data['action']
            if draft['status'] == 'published':
                raise NewsError('게시 중단하거나 새 수정본을 저장하세요.')
            if action == 'approved':
                if draft['status'] != 'in_review':
                    raise NewsError('문장별 검토를 마친 검토 중 기사만 승인할 수 있습니다.')
                need(data.get('checks'), '최종 검토 항목 4개를 모두 확인하세요.', 422)
                digest = self.approvable(tx, draft, topic)
                tx.execute("UPDATE news_drafts SET status='approved',approved_by=%s,approved_at=NOW() WHERE id=%s", (editor, draft_id))
            else:
                digest = draft['fact_snapshot_sha256']
                status = 'in_review' if action == 'submitted' else action
                tx.execute('UPDATE news_drafts SET status=%s,approved_by=NULL,approved_at=NULL WHERE id=%s', (status, draft_id))
            reason = data['reason']
            if action == 'approved':
                reason += '\n검토: 수치 / 시점·지역 / 인과·과장 / 출처·이용 조건 모두 확인'
            self.review_log(tx, draft_id, action, editor, reason, digest, draft['content_hash'])
            return {'ok': True, 'status': 'in_review' if action == 'submitted' else action}

    # 승인 기록이 지금의 내용·근거와 일치할 때만 게시합니다. 이전 게시본 교체도 같은 트랜잭션입니다.
    def publish(self, draft_id, data, editor):
        with self.db.transaction() as tx:
            draft, topic = self.draft(tx, draft_id, True)
            self.expected(draft, data['expected_content_hash'])
            if draft['status'] not in ('approved', 'published'):
                raise NewsError('사람의 최종 승인이 필요합니다.')
            digest = self.approvable(tx, draft, topic)
            approval = tx.one("SELECT * FROM news_reviews WHERE draft_id=%s AND action='approved' ORDER BY id DESC LIMIT 1", (draft_id,))
            if not approval or approval['content_sha256'] != draft['content_hash'] or approval['fact_snapshot_sha256'] != digest:
                raise NewsError('현재 기사 내용·근거와 일치하는 최종 승인이 없습니다.')
            previous = tx.all("SELECT draft_id FROM news_publications WHERE topic_id=%s AND status='published' AND draft_id<>%s", (topic['id'], draft_id))
            for old in previous:
                tx.execute("UPDATE news_drafts SET status='changes_requested',approved_by=NULL,approved_at=NULL WHERE id=%s", (old['draft_id'],))
                self.review_log(tx, old['draft_id'], 'unpublished', editor, '새 수정본으로 교체')
            tx.execute("UPDATE news_publications SET status='unpublished',unpublished_at=NOW(),retraction_reason='새 수정본으로 교체' WHERE topic_id=%s AND status='published' AND draft_id<>%s", (topic['id'], draft_id))
            publication = tx.one('SELECT id FROM news_publications WHERE draft_id=%s', (draft_id,))
            if publication:
                ident = publication['id']
                tx.execute("UPDATE news_publications SET status='published',published_at=NOW(),unpublished_at=NULL,retraction_reason=NULL WHERE id=%s", (ident,))
            else:
                ident = tx.insert("INSERT INTO news_publications(topic_id,draft_id,slug,status,published_at) VALUES(%s,%s,%s,'published',NOW())", (topic['id'], draft_id, 'news-' + str(topic['id']) + '-' + str(draft_id)))
            tx.execute("UPDATE news_drafts SET status='published' WHERE id=%s", (draft_id,))
            self.review_log(tx, draft_id, 'published', editor, '최종 승인 버전 게시', digest, draft['content_hash'])
            return {'ok': True, 'id': ident, 'status': 'published'}

    # 중단 사유와 이력을 남기고 공개 상태를 해제합니다. 재게시하려면 다시 승인해야 합니다.
    def unpublish(self, draft_id, data, editor):
        with self.db.transaction() as tx:
            draft, _ = self.draft(tx, draft_id, True)
            need(tx.one("SELECT id FROM news_publications WHERE draft_id=%s AND status='published'", (draft_id,)), '게시 중인 기사가 아닙니다.', 409)
            tx.execute("UPDATE news_publications SET status='unpublished',unpublished_at=NOW(),retraction_reason=%s WHERE draft_id=%s", (data['reason'], draft_id))
            tx.execute("UPDATE news_drafts SET status='changes_requested',approved_by=NULL,approved_at=NULL WHERE id=%s", (draft_id,))
            self.review_log(tx, draft_id, 'unpublished', editor, data['reason'], draft['fact_snapshot_sha256'], draft['content_hash'])
            return {'ok': True, 'status': 'unpublished'}

    # 게시·승인·근거를 다시 검사한 기사만 공개합니다. 검증 메모·키·내부 해시는 사용자에게 보내지 않습니다.
    def public(self, district_id=None, publication_id=None, limit=12):
        with self.db.transaction() as tx:
            where = "p.status='published' AND a.status='published' AND a.is_demo=0 AND t.is_demo=0"
            args = []
            if district_id:
                where += ' AND t.district_id=%s'
                args.append(district_id)
            if publication_id:
                where += ' AND p.id=%s'
                args.append(publication_id)
            rows = tx.all('SELECT p.id,p.draft_id,p.published_at,p.slug FROM news_publications p JOIN news_drafts a ON a.id=p.draft_id JOIN news_topics t ON t.id=p.topic_id WHERE ' + where + ' ORDER BY p.published_at DESC,p.id DESC LIMIT 100', tuple(args))
            output = []
            for row in rows:
                draft, topic = self.draft(tx, row['draft_id'])
                try:
                    digest = self.approvable(tx, draft, topic)
                except NewsError:
                    continue
                approval = tx.one("SELECT content_sha256,fact_snapshot_sha256 FROM news_reviews WHERE draft_id=%s AND action='approved' ORDER BY id DESC LIMIT 1", (draft['id'],))
                if not approval or approval['content_sha256'] != draft['content_hash'] or approval['fact_snapshot_sha256'] != digest:
                    continue
                sources = tx.all('''SELECT DISTINCT s.id,s.source_title,s.organization,s.source_url,s.published_at
                    FROM news_sources s JOIN news_fact_evidence e ON e.source_id=s.id
                    JOIN news_claim_facts f ON f.fact_id=e.fact_id JOIN news_claims c ON c.id=f.claim_id
                    WHERE c.draft_id=%s ORDER BY s.id''', (draft['id'],))
                output.append({'id': row['id'], 'slug': row['slug'], 'title': draft['title'],
                               'summary': draft['summary_text'], 'body': draft['body_text'],
                               'district_id': topic['district_id'], 'region_name': topic['region_name'],
                               'category': topic['category'], 'published_at': row['published_at'],
                               'sources': sources, 'ai_assisted': True})
                if len(output) >= limit:
                    break
            if publication_id:
                return need(output, '게시된 기사를 찾지 못했습니다.')[0]
            return output
