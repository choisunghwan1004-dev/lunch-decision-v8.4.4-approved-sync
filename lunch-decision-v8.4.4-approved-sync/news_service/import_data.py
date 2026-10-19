"""CSV/JSON 원자료 수집 → MySQL 저장. 검증·AI 생성·게시를 자동 실행하지 않습니다."""
import csv
import hashlib
from io import StringIO
import json

from pydantic import ValidationError

from .schemas import EvidenceInput, FactInput, SourceInput
from .service import NewsError
from .validation import validate_source

SOURCE_FIELDS = set(SourceInput.model_fields)
FACT_FIELDS = set(FactInput.model_fields)
EXTRA_FIELDS = {'excerpt_reference', 'evidence_note', 'is_demo'}
MAX_ROWS = 40


def parse_records(format_name, content):
    """CSV의 따옴표·줄바꿈과 UTF-8 BOM을 처리하고 전체 행을 먼저 검사합니다."""
    content = content.lstrip('\ufeff')
    try:
        if format_name == 'csv':
            reader = csv.DictReader(StringIO(content, newline=''))
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise NewsError('CSV 헤더가 없거나 중복되었습니다.', 422)
            raw_rows = []
            for row in reader:
                if len(raw_rows) >= MAX_ROWS:
                    raise NewsError('한 번에 최대 40행까지 가져올 수 있습니다.', 422)
                raw_rows.append(row)
        elif format_name == 'json':
            raw_rows = json.loads(content)
        else:
            raise NewsError('CSV 또는 JSON 파일을 선택하세요.', 422)
    except (csv.Error, json.JSONDecodeError) as error:
        raise NewsError('파일의 CSV/JSON 문법을 확인하세요.', 422) from error
    if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= MAX_ROWS:
        raise NewsError('파일은 1~40개의 객체/행 목록이어야 합니다.', 422)
    result, seen = [], set()
    for index, raw in enumerate(raw_rows, 1):
        if not isinstance(raw, dict) or set(raw) - (SOURCE_FIELDS | FACT_FIELDS | EXTRA_FIELDS):
            raise NewsError(f'{index}행: 지원하지 않는 필드 또는 잘못된 열 수입니다.', 422)
        # 빈 CSV 칸은 선택 필드에서 None으로 변환합니다. 필수값은 Pydantic이 거절합니다.
        row = {key: value if value != '' else None for key, value in raw.items()}
        try:
            source = SourceInput.model_validate({k: v for k, v in row.items() if k in SOURCE_FIELDS}).model_dump()
            fact = FactInput.model_validate({k: v for k, v in row.items() if k in FACT_FIELDS}).model_dump()
            evidence = EvidenceInput.model_validate({'source_id': 1, 'excerpt_reference': row.get('excerpt_reference'),
                                                     'evidence_note': row.get('evidence_note')}).model_dump()
            validate_source(source)
        except (ValueError, ValidationError) as error:
            raise NewsError(f'{index}행: 필수 출처·Fact·기간·근거 필드를 확인하세요.', 422) from error
        flag = row.get('is_demo')
        if flag is True or str(flag).lower() in ('1', 'true'):
            demo = True
        elif flag is False or str(flag).lower() in ('0', 'false'):
            demo = False
        else:
            raise NewsError(f'{index}행: is_demo는 true/false 또는 1/0을 명시하세요.', 422)
        if fact['fact_key'] in seen:
            raise NewsError(f'{index}행: 파일 안의 Fact Key가 중복되었습니다.', 409)
        seen.add(fact['fact_key'])
        result.append({'source': source, 'fact': fact, 'evidence': evidence, 'is_demo': demo})
    return result


def import_records(service, topic_id, format_name, content, editor):
    """단 한 행이라도 충돌하면 전체 롤백합니다. 기존 출처·Fact를 덮어쓰지 않습니다."""
    rows = parse_records(format_name, content)
    source_count = 0
    with service.db.transaction() as tx:
        topic = service.topic(tx, topic_id, True)
        for index, row in enumerate(rows, 1):
            if row['is_demo'] and not topic['is_demo']:
                raise NewsError('시연 파일은 시연용 주제에만 가져올 수 있습니다.', 422)
            fact, source, evidence = row['fact'], row['source'], row['evidence']
            if tx.one('SELECT id FROM news_facts WHERE topic_id=%s AND fact_key=%s', (topic_id, fact['fact_key'])):
                raise NewsError(f'{index}행: 같은 Fact Key가 이미 있습니다. 전체 가져오기를 취소했습니다.', 409)
            digest = hashlib.sha256(source['source_url'].encode()).hexdigest()
            old = tx.one('SELECT * FROM news_sources WHERE topic_id=%s AND source_url_sha256=UNHEX(%s)', (topic_id, digest))
            if old:
                # 동일 URL의 내용이 다르면 묵시적으로 수정하지 않습니다. 기존 기사 근거 보호가 우선입니다.
                matches = all(str(old.get(k)) == str(value) for k, value in source.items())
                if not matches:
                    raise NewsError(f'{index}행: 기존 URL의 원자료 내용이 다릅니다. 출처 수정 화면에서 확인하세요.', 409)
                source_id = old['id']
            else:
                source_id = tx.insert('''INSERT INTO news_sources(topic_id,source_kind,organization,source_title,source_url,
                    source_url_sha256,published_at,source_excerpt,license_note,content_sha256,is_demo,checked_at)
                    VALUES(%s,%s,%s,%s,%s,UNHEX(%s),%s,%s,%s,%s,%s,NOW())''',
                    (topic_id, source['source_kind'], source['organization'], source['source_title'], source['source_url'],
                     digest, source['published_at'], source['source_excerpt'], source['license_note'],
                     hashlib.sha256(source['source_excerpt'].encode()).hexdigest(), topic['is_demo']))
                source_count += 1
            values = tuple(fact.get(k) for k in ('fact_key','fact_type','value_text','value_number','unit','event_start','event_end'))
            fact_id = tx.insert("INSERT INTO news_facts(topic_id,fact_key,fact_type,value_text,value_number,unit,event_start,event_end,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'candidate')", (topic_id, *values))
            tx.execute('INSERT INTO news_fact_evidence(fact_id,source_id,excerpt_reference,evidence_note,checked_at) VALUES(%s,%s,%s,%s,NOW())',
                       (fact_id, source_id, evidence['excerpt_reference'], evidence['evidence_note']))
    return {'ok': True, 'facts_created': len(rows), 'sources_created': source_count, 'status': 'candidate',
            'message': '가져왔습니다. 원문을 직접 대조한 뒤 Fact를 검증하세요.'}
