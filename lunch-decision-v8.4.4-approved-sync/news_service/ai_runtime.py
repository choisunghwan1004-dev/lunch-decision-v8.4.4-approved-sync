"""OpenAI 설정·연결·오류 안내를 한곳에서 관리합니다. 키 원문은 반환하지 않습니다."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gpt-6-luna'
# 실행 폴더와 무관하게 프로젝트 루트 설정을 읽습니다. OS 환경 변수는 우선합니다.
load_dotenv(ROOT / '.env', encoding='utf-8-sig')


class NewsAIError(ValueError):
    """HTTP 응답·CLI·사용량 기록에 쓸 수 있는 비밀 정보 없는 오류입니다."""
    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def configuration():
    """무료 설정 확인입니다. 키가 있다는 사실과 실제 호출 성공은 구분합니다."""
    return {'ok': True, 'model': MODEL,
            'key_configured': bool(os.getenv('OPENAI_API_KEY', '').strip()),
            'model_configured': os.getenv('OPENAI_NEWS_MODEL', MODEL).strip() == MODEL,
            'live_verified': False}


def validate_configuration(require_key=True):
    state = configuration()
    if not state['model_configured']:
        raise NewsAIError('model_configuration', 'OPENAI_NEWS_MODEL을 gpt-6-luna로 설정하고 FastAPI를 다시 시작하세요.', 503)
    if require_key and not state['key_configured']:
        raise NewsAIError('missing_api_key', 'OPENAI_API_KEY가 없습니다. 13_OpenAI_키설정.bat을 실행한 뒤 FastAPI를 다시 시작하세요.', 503)


def create_client():
    validate_configuration()
    # 공식 서버만 사용합니다. 다른 용도의 OPENAI_BASE_URL 환경 값으로 키가 전달되지 않습니다.
    # 자동 재시도를 끄므로 잔액 부족이나 응답 지연 때 호출을 반복하지 않습니다.
    return OpenAI(api_key=os.environ['OPENAI_API_KEY'].strip(),
                  base_url='https://api.openai.com/v1', timeout=35, max_retries=0)


def provider_error(error):
    """공급자의 원문 메시지에는 민감한 내용이 있을 수 있어 정해진 안내만 사용합니다."""
    if isinstance(error, APITimeoutError):
        return NewsAIError('timeout', 'OpenAI 응답 시간이 초과됐습니다. 자동 재시도하지 않았습니다. 사용량을 확인한 뒤 다시 실행하세요.', 504)
    if isinstance(error, APIConnectionError):
        return NewsAIError('connection', 'OpenAI에 연결하지 못했습니다. 인터넷·방화벽·프록시 설정을 확인하세요.', 503)
    if isinstance(error, APIStatusError):
        status = error.status_code
        body = error.body if isinstance(error.body, dict) else {}
        detail = body.get('error', body)
        code = detail.get('code') if isinstance(detail, dict) else None
        if status == 401:
            return NewsAIError('invalid_api_key', 'OpenAI 키가 유효하지 않습니다. API Keys에서 새 키를 발급받아 13번 파일로 설정하세요.')
        if status in (403, 404):
            return NewsAIError('model_access', 'gpt-6-luna 모델 또는 프로젝트 권한이 없습니다. API 프로젝트의 모델·Responses 권한을 확인하세요. 다른 모델로 자동 변경하지 않습니다.')
        if status == 429:
            if code in ('insufficient_quota', 'billing_hard_limit_reached'):
                return NewsAIError('insufficient_quota', 'OpenAI API 잔액 또는 예산이 부족합니다. API Billing과 프로젝트 한도를 확인하세요.', 429)
            return NewsAIError('rate_limit', 'OpenAI 호출 한도에 도달했습니다. 잠시 뒤 다시 실행하세요. 자동 재시도하지 않았습니다.', 429)
        if status == 400:
            return NewsAIError('invalid_request', 'OpenAI가 요청 형식을 거절했습니다. 모델 권한과 SDK 설치 버전을 확인하세요.')
    return NewsAIError('provider_error', 'OpenAI 처리에 실패했습니다. API 상태와 계정 설정을 확인하세요. 자동 재시도하지 않았습니다.')
