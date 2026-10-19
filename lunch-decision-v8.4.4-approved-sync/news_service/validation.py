# 공통 검사: HTTPS 출처·Fact 형식·문장별 Fact 연결을 확인합니다.
# snapshot은 저장할 근거 묶음, fingerprint는 그 내용의 변경 여부를 비교하는 SHA-256 지문입니다.
# 해시는 변경 감지 도구이며 원자료의 진위를 증명하지 않습니다.

"""Extended source/fact/claim checks from feature/v8.5.1-news-center."""
import hashlib
import json
from urllib.parse import urlsplit
from .schemas import ArticleInput, FactInput


# 출처 링크의 HTTPS 형식과 인증 정보 포함 여부를 검사합니다. 서버가 해당 URL을 수집하지는 않습니다.
def validate_source(source):
    url = source['source_url']
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('인증 정보가 없는 HTTPS 출처 URL을 입력하세요.')
    return source['organization'], source['source_title'], url


# DB 행에서 입력에 해당하는 필드만 골라 Pydantic 규칙으로 다시 검사합니다.
def validate_fact(fact):
    allowed = set(FactInput.model_fields)
    parsed = FactInput.model_validate({key: value for key, value in fact.items() if key in allowed})
    return parsed.fact_key, parsed.fact_type, parsed.value_text


# 유효한 Fact·연결 출처·직접 대조 체크·검증 의견이 모두 있어야 검증 완료로 바꿉니다.
def can_verify(fact, evidence_count, confirmed, note):
    validate_fact(fact)
    if not evidence_count:
        raise ValueError('원자료 출처를 먼저 연결하세요.')
    if confirmed is not True or not str(note or '').strip():
        raise ValueError('원문 직접 대조와 검증 의견이 필요합니다.')
    return True


# 구형 출처라도 URL·공개 시점·구절·이용 조건이 갖춰진 경우에만 생성 근거로 인정합니다.
def complete_evidence(source):
    try:
        validate_source(source)
    except (ValueError, TypeError):
        return False
    return bool(source.get('organization') and source.get('source_title') and source.get('published_at')
                and len(str(source.get('source_excerpt') or '').strip()) >= 10
                and str(source.get('license_note') or '').strip())


# 정렬된 JSON을 해시로 바꿉니다. 같은 내용은 같은 지문이 되도록 키 순서와 공백을 고정합니다.
def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), default=str).encode()).hexdigest()


# Fact 값을 Key 순서로 정렬하고 원자료 연결을 함께 묶어 과거 근거를 보존합니다.
def snapshot(facts):
    fields = ('id', 'fact_key', 'fact_type', 'value_text', 'value_number', 'unit',
              'event_start', 'event_end', 'verification_note', 'verified_by', 'verified_at')
    return [{**{key: fact.get(key) for key in fields}, 'evidence': fact.get('evidence', [])}
            for fact in sorted(facts, key=lambda item: item['fact_key'])]


# AI/수정본 형식을 검사하고 알려진 검증 Fact만 허용합니다. 본문은 문장 배열로부터 직접 만듭니다.
def parse_draft(raw, keys):
    try:
        article = ArticleInput.model_validate_json(raw) if isinstance(raw, str) else ArticleInput.model_validate(raw)
    except ValueError as error:
        raise ValueError('기사 제목·문장·Fact 연결 형식을 확인하세요.') from error
    data = article.model_dump()
    for claim in [{'sentence': data['title'], 'fact_keys': data['title_fact_keys']}, *data['claims']]:
        if any(key not in keys for key in claim['fact_keys']):
            raise ValueError('검증되지 않은 Fact Key를 인용한 문장이 있습니다.')
    data['title_fact_keys'] = list(dict.fromkeys(data['title_fact_keys']))
    for claim in data['claims']:
        claim['fact_keys'] = list(dict.fromkeys(claim['fact_keys']))
    # Body is constructed from the evidence-linked sentences, never a separate AI field.
    data['body'] = '\n\n'.join(claim['sentence'] for claim in data['claims'])
    if len(data['body']) > 7000:
        raise ValueError('본문은 7,000자 이내로 작성하세요.')
    return data


# 제목·본문·문장 순서·Fact 연결의 지문입니다. 검토 메모는 기사 본문이 아니므로 포함하지 않습니다.
def content_hash(draft, claims):
    return fingerprint({'title': draft['title'], 'body': draft['body_text'],
                        'claims': [{'sequence_no': c['sequence_no'], 'statement_text': c['statement_text'],
                                    'fact_keys': sorted(c['fact_keys'])} for c in claims]})
