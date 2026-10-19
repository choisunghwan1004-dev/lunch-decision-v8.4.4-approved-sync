"""Internal FastAPI service; browser access goes through the existing Node session."""
import hmac
import logging
import os
import re
from urllib.parse import unquote

from fastapi import Depends, FastAPI, Header, Query
from fastapi.responses import JSONResponse

from . import schemas as s
from .article_ai import MODEL
from .service import NewsError, NewsService

app = FastAPI(title='V8.4.4 뉴스 운영 API', version='8.5.2', docs_url=None, redoc_url=None, openapi_url=None)
log = logging.getLogger('news')


def auth(x_news_internal_token: str | None = Header(None)):
    token = os.getenv('NEWS_INTERNAL_TOKEN', '')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', token) or not x_news_internal_token or not hmac.compare_digest(token, x_news_internal_token):
        raise NewsError('뉴스 내부 인증에 실패했습니다.', 403)


def editor(x_news_editor: str = Header('admin')):
    return unquote(x_news_editor).strip()[:100] or 'admin'


def get_service():
    return NewsService()


@app.exception_handler(NewsError)
async def news_error(_, error):
    return JSONResponse(status_code=error.status, content={'ok': False, 'detail': error.message})


@app.exception_handler(ValueError)
async def value_error(_, error):
    return JSONResponse(status_code=422, content={'ok': False, 'detail': str(error)})


@app.exception_handler(Exception)
async def service_error(_, error):
    log.error('news service error: %s code=%s', type(error).__name__, getattr(error, 'errno', ''))
    return JSONResponse(status_code=503, content={'ok': False, 'detail': '뉴스 DB/API에 연결할 수 없습니다. 설치·스키마·서버 로그를 확인하세요.'})


AUTH = [Depends(auth)]


@app.get('/health', dependencies=AUTH)
def health(service: NewsService = Depends(get_service)):
    with service.db.transaction() as tx:
        row = tx.one("SELECT version FROM news_schema_version WHERE name='news'")
        if not row or row['version'] != '8.5.2':
            raise NewsError('python -m news_service.setup 실행이 필요합니다.', 503)
    return {'ok': True, 'version': '8.5.2', 'model': MODEL,
            'openaiConfigured': bool(os.getenv('OPENAI_API_KEY')),
            'modelConfigured': os.getenv('OPENAI_NEWS_MODEL', MODEL) == MODEL}


@app.get('/regions', dependencies=AUTH)
def regions(service: NewsService = Depends(get_service)):
    return service.regions()


@app.get('/topics', dependencies=AUTH)
def topics(service: NewsService = Depends(get_service)):
    return service.topics()


@app.post('/topics', status_code=201, dependencies=AUTH)
def new_topic(data: s.TopicInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.create_topic(data.model_dump(), who)


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


@app.post('/drafts/{draft_id}/unpublish', dependencies=AUTH)
def unpublish(draft_id: int, data: s.ReasonInput, who: str = Depends(editor), service: NewsService = Depends(get_service)):
    return service.unpublish(draft_id, data.model_dump(), who)


@app.get('/public', dependencies=AUTH)
def public(district_id: int | None = Query(None, gt=0), limit: int = Query(12, ge=1, le=30), service: NewsService = Depends(get_service)):
    return service.public(district_id=district_id, limit=limit)


@app.get('/public/{publication_id}', dependencies=AUTH)
def public_detail(publication_id: int, service: NewsService = Depends(get_service)):
    return service.public(publication_id=publication_id)
