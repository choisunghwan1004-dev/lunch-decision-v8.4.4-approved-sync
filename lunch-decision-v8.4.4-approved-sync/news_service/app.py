# 입구 역할: Node 프록시가 전달한 HTTP 요청을 받아 검사한 후 NewsService에 맡깁니다.
# 읽는 순서: 인증(auth) → 입력 형식(schemas.py) → 업무 처리(service.py) → MySQL(db.py).
# 화면의 /api/news 접두사는 Node에서 제거하므로 Python 경로에는 /topics처럼 적습니다.

"""Internal FastAPI service; browser access goes through the existing Node session."""
import hmac
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import unquote

from fastapi import Depends, FastAPI, Header, Query
from fastapi.responses import JSONResponse

from . import schemas as s
from .article_ai import MODEL
from .ai_runtime import NewsAIError, configuration
from .openai_check import live_check
from .service import NewsError, NewsService

app = FastAPI(title='V8.4.4 뉴스 운영 API', version='8.5.2', docs_url=None, redoc_url=None, openapi_url=None)
log = logging.getLogger('news')


# Node만 아는 64자리 내부 토큰을 비교합니다. 공개 기사 조회도 이 내부 인증을 거칩니다.
def auth(x_news_internal_token: str | None = Header(None)):
    token = os.getenv('NEWS_INTERNAL_TOKEN', '')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', token) or not x_news_internal_token or not hmac.compare_digest(token, x_news_internal_token):
        raise NewsError('뉴스 서버의 연결 설정이 다릅니다. 18_뉴스_연결복구.bat 실행 후 기존 Node·FastAPI 창을 모두 종료하고 09번을 다시 실행하세요.', 403)


# Node가 세션에서 정한 검토자 이름을 복원합니다. 브라우저 입력으로 검토자를 지정하지 않습니다.
def editor(x_news_editor: str = Header('admin')):
    return unquote(x_news_editor).strip()[:100] or 'admin'


# 요청 처리에 사용할 업무 객체를 만듭니다. 테스트는 이 의존성을 대역으로 바꿀 수 있습니다.
def get_service():
    return NewsService()


# 업무상 거절 사유와 상태 코드(404·409 등)를 화면에 전달합니다.
@app.exception_handler(NewsError)
async def news_error(_, error):
    return JSONResponse(status_code=error.status, content={'ok': False, 'detail': error.message})


# 입력 내용이나 AI 출력의 형식 오류를 HTTP 422로 전달합니다.
@app.exception_handler(ValueError)
async def value_error(_, error):
    return JSONResponse(status_code=422, content={'ok': False, 'detail': str(error)})


# 예상하지 못한 DB/API 오류를 감춥니다. 연결 정보나 비밀 키를 응답으로 보내지 않습니다.
@app.exception_handler(Exception)
async def service_error(_, error):
    log.error('news service error: %s code=%s', type(error).__name__, getattr(error, 'errno', ''))
    # 설치 문제를 빈 선택 목록으로 숨기지 않도록 다음 행동을 안내합니다. 연결 정보는 보내지 않습니다.
    messages = {
        1045: ('news_db_auth', '뉴스 DB에 로그인하지 못했습니다. 프로젝트 .env의 DB_USER·DB_PASSWORD를 확인하고 서버를 다시 시작하세요.'),
        1049: ('news_database_missing', '운영 DB가 없습니다. .env의 V83_DB_NAME과 npm run setup 결과를 확인하세요.'),
        1146: ('news_schema_missing', '뉴스 테이블 설치가 필요합니다. 18_뉴스_연결복구.bat을 실행하세요.'),
        2003: ('news_db_unavailable', 'MySQL 서버에 연결하지 못했습니다. MySQL 서비스·DB_HOST·DB_PORT를 확인하세요.'),
    }
    if getattr(error, 'errno', None) in messages:
        code, detail = messages[error.errno]
        return JSONResponse(status_code=503, content={'ok': False, 'detail': detail, 'code': code})
    return JSONResponse(status_code=503, content={'ok': False, 'detail': '뉴스 DB/API에 연결할 수 없습니다. 설치·스키마·서버 로그를 확인하세요.'})


AUTH = [Depends(auth)]

# 시작할 때 읽어 둡니다. 파일만 덮어쓰고 옛 Python 프로세스를 계속 쓰면 진단에서 구분됩니다.
RELEASE = json.loads(Path(__file__).with_name('release.json').read_text(encoding='utf-8'))


@app.get('/public/version', dependencies=AUTH)
def public_version():
    # DB·OpenAI·노션을 호출하지 않는 읽기 전용 설치 진단입니다. 비밀 설정은 반환하지 않습니다.
    # Node 실행기와 같은 규칙으로 폴더 지문을 만듭니다. 실제 경로·키는 응답에 넣지 않습니다.
    import hashlib
    canonical = os.path.realpath(str(Path(__file__).resolve().parents[1]))
    if os.name == 'nt':
        canonical = canonical.replace('\\', '/').lower()
    return {**RELEASE, 'project_root_id': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
            'launcher_protocol': 'oneclick-v1'}


# 원문 API 오류 대신 안전한 코드와 해결 방법을 관리자에게 전달합니다.
@app.exception_handler(NewsAIError)
async def ai_error(_, error):
    return JSONResponse(status_code=error.status, content={'ok': False, 'detail': error.message, 'code': error.code})


# DB가 준비되기 전에도 키·모델 설정을 확인할 수 있습니다. 이 GET은 유료 호출이 없습니다.
@app.get('/ai/status', dependencies=AUTH)
def ai_status():
    return configuration()


# 관리자만 고정 가상 자료를 전송합니다. DB의 운영 자료·검증·승인 상태를 변경하지 않습니다.
@app.post('/ai/check', dependencies=AUTH)
def ai_check(data: s.AICheckInput):
    return live_check()


# 스키마 버전과 키 설정 여부를 확인합니다. 키가 있다는 표시만으로 실제 API 호출 성공을 뜻하지 않습니다.
@app.get('/health', dependencies=AUTH)
def health(service: NewsService = Depends(get_service)):
    with service.db.transaction() as tx:
        row = tx.one("SELECT version FROM news_schema_version WHERE name='news'")
        if not row or row['version'] != '8.5.2':
            raise NewsError('뉴스 스키마 설치가 필요합니다. 18_뉴스_연결복구.bat을 실행하세요.', 503)
    return {'ok': True, 'version': '8.5.2', 'model': MODEL,
            'openaiConfigured': configuration()['key_configured'],
            'modelConfigured': configuration()['model_configured']}


@app.get('/regions', dependencies=AUTH)
def regions(service: NewsService = Depends(get_service)):
    return service.regions()


@app.get('/topics', dependencies=AUTH)
def topics(service: NewsService = Depends(get_service)):
    return service.topics()


@app.post('/topics', status_code=201, dependencies=AUTH)
def new_topic(data: s.TopicInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.create_topic(data.model_dump(), who)


# CSV·JSON 파일의 모든 행을 검사하고 한 트랜잭션에서 후보 Fact로 저장합니다.
@app.post('/topics/{topic_id}/import', status_code=201, dependencies=AUTH)
def import_file(topic_id: int, data: s.ImportInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    from .import_data import import_records
    return import_records(service, topic_id, data.format, data.content, who)


@app.get('/topics/{topic_id}/sources', dependencies=AUTH)
def sources(topic_id: int, service: NewsService = Depends(get_service)):
    return service.sources(topic_id)


@app.post('/topics/{topic_id}/sources', status_code=201, dependencies=AUTH)
def new_source(topic_id: int, data: s.SourceInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.save_source(topic_id, data.model_dump(), who)


@app.put('/topics/{topic_id}/sources/{source_id}', dependencies=AUTH)
def update_source(topic_id: int, source_id: int, data: s.SourceInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.save_source(topic_id, data.model_dump(), who, source_id)


@app.delete('/topics/{topic_id}/sources/{source_id}', dependencies=AUTH)
def delete_source(topic_id: int, source_id: int, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.delete_source(topic_id, source_id, who)


@app.get('/topics/{topic_id}/facts', dependencies=AUTH)
def facts(topic_id: int, service: NewsService = Depends(get_service)):
    return service.facts(topic_id)


@app.post('/topics/{topic_id}/facts', status_code=201, dependencies=AUTH)
def new_fact(topic_id: int, data: s.FactInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.save_fact(topic_id, data.model_dump(), who)


@app.put('/topics/{topic_id}/facts/{fact_id}', dependencies=AUTH)
def update_fact(topic_id: int, fact_id: int, data: s.FactInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.save_fact(topic_id, data.model_dump(), who, fact_id)


@app.delete('/topics/{topic_id}/facts/{fact_id}', dependencies=AUTH)
def delete_fact(topic_id: int, fact_id: int, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.delete_fact(topic_id, fact_id, who)


@app.post('/topics/{topic_id}/facts/{fact_id}/evidence', dependencies=AUTH)
def evidence(topic_id: int, fact_id: int, data: s.EvidenceInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.evidence(topic_id, fact_id, data.model_dump(), who)


@app.delete('/topics/{topic_id}/facts/{fact_id}/evidence/{source_id}', dependencies=AUTH)
def remove_evidence(topic_id: int, fact_id: int, source_id: int, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.evidence(topic_id, fact_id, {'source_id': source_id}, who, delete=True)


@app.post('/topics/{topic_id}/facts/{fact_id}/verify', dependencies=AUTH)
def verify_fact(topic_id: int, fact_id: int, data: s.VerifyInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.verify_fact(topic_id, fact_id, data.model_dump(), who)


@app.post('/topics/{topic_id}/facts/{fact_id}/status', dependencies=AUTH)
def fact_status(topic_id: int, fact_id: int, data: s.FactStatusInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.fact_status(topic_id, fact_id, data.model_dump(), who)


@app.get('/topics/{topic_id}/fact-sheet', dependencies=AUTH)
def fact_sheet(topic_id: int, service: NewsService = Depends(get_service)):
    return service.fact_sheet(topic_id)


@app.post('/topics/{topic_id}/generate', status_code=201, dependencies=AUTH)
def generate(topic_id: int, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.generate(topic_id, who)


@app.get('/topics/{topic_id}/drafts', dependencies=AUTH)
def drafts(topic_id: int, service: NewsService = Depends(get_service)):
    return service.drafts(topic_id)


@app.get('/drafts/{draft_id}', dependencies=AUTH)
def detail(draft_id: int, service: NewsService = Depends(get_service)):
    return service.detail(draft_id)


@app.post('/drafts/{draft_id}/revisions', status_code=201, dependencies=AUTH)
def edit_draft(draft_id: int, data: s.EditInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.edit(draft_id, data.model_dump(), who)


@app.post('/drafts/{draft_id}/claims/{claim_id}/review', dependencies=AUTH)
def check_claim(draft_id: int, claim_id: int, data: s.ClaimReviewInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.check_claim(draft_id, claim_id, data.model_dump(), who)


@app.post('/drafts/{draft_id}/review', dependencies=AUTH)
def review(draft_id: int, data: s.ReviewInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.review(draft_id, data.model_dump(), who)


@app.post('/drafts/{draft_id}/publish', dependencies=AUTH)
def publish(draft_id: int, data: s.PublishInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.publish(draft_id, data.model_dump(), who)


@app.post('/drafts/{draft_id}/verify-and-save', dependencies=AUTH)
def verify_and_save(draft_id: int, data: s.VerifyAndSaveInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.verify_and_save(draft_id, data.model_dump(), who)


@app.post('/drafts/{draft_id}/ai-review', dependencies=AUTH)
def assisted_review(draft_id: int, data: s.AIReviewInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.assisted_review(draft_id, data.model_dump(), who)


@app.post('/drafts/{draft_id}/unpublish', dependencies=AUTH)
def unpublish(draft_id: int, data: s.ReasonInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.unpublish(draft_id, data.model_dump(), who)


@app.get('/public', dependencies=AUTH)
def public(district_id: int | None = Query(None, gt=0), limit: int = Query(12, ge=1, le=30), service: NewsService = Depends(get_service)):
    return service.public(district_id=district_id, limit=limit)


# 고정 경로를 /public/{publication_id}보다 먼저 선언하여 'feed'를 기사 ID로 해석하지 않게 합니다.
@app.get('/public/feed', dependencies=AUTH)
def public_feed(district_id: int | None = Query(None, gt=0), limit: int = Query(30, ge=1, le=30), service: NewsService = Depends(get_service)):
    return service.public_feed(district_id=district_id, limit=limit)


@app.get('/public/facts/{topic_id}', dependencies=AUTH)
def public_facts(topic_id: int, district_id: int | None = Query(None, gt=0), service: NewsService = Depends(get_service)):
    return service.public_facts(topic_id=topic_id, district_id=district_id)


@app.get('/public/{publication_id}', dependencies=AUTH)
def public_detail(publication_id: int, district_id: int | None = Query(None, gt=0), service: NewsService = Depends(get_service)):
    return service.public(publication_id=publication_id, district_id=district_id)
