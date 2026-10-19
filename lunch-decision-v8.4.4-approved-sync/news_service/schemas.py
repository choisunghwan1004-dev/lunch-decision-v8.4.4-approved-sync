# 입력 계약서: API가 받을 필드 이름·자료형·길이·선택 가능한 값을 선언합니다.
# Pydantic 검사가 통과해야 service.py가 호출되며, 잘못된 입력은 HTTP 422가 됩니다.
# Literal[True]는 확인 체크가 반드시 참이어야 한다는 뜻입니다. AI의 사실 판정이 아닙니다.

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# 모든 입력의 공통 규칙: 정의하지 않은 필드를 거절하고 문자열 양끝 공백을 정리합니다.
class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


# 뉴스가 속한 실제 시군구 PK와 주제·분류·시연 여부를 받습니다.
class TopicInput(Input):
    district_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=200)
    category: Literal['festival', 'tourism', 'transport', 'culture', 'other'] = 'tourism'
    is_demo: bool = False


# 사람이 읽은 원자료 URL·공개 시점·구절·이용 조건을 필수로 받습니다.
class SourceInput(Input):
    source_kind: Literal['official', 'public_api', 'csv', 'manual', 'other'] = 'official'
    organization: str = Field(min_length=1, max_length=200)
    source_title: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=8, max_length=1024)
    published_at: datetime
    source_excerpt: str = Field(min_length=10, max_length=16000)
    license_note: str = Field(min_length=1, max_length=500)

    # 시간대 정보가 있으면 UTC로 변환한 뒤 MySQL DATETIME에 넣을 형태로 정리합니다.
    @field_validator('published_at')
    @classmethod
    def utc_date(cls, value):
        if value.tzinfo:
            from datetime import timezone
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


# Fact Key와 사실 값을 받습니다. 수치·가격은 별도 숫자 값도 필요합니다.
class FactInput(Input):
    fact_key: str = Field(pattern=r'^[A-Za-z0-9_-]{2,80}$')
    fact_type: Literal['text', 'date', 'date_range', 'number', 'price', 'place', 'time']
    value_text: str = Field(min_length=1, max_length=4000)
    value_number: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    unit: str | None = Field(default=None, max_length=30)
    event_start: date | None = None
    event_end: date | None = None

    # 필드 하나만으로 판단할 수 없는 수치 필수 조건과 기간의 앞뒤 관계를 검사합니다.
    @model_validator(mode='after')
    def valid_fact(self):
        if self.fact_type in ('number', 'price') and self.value_number is None:
            raise ValueError('수치 Fact에는 수치 값이 필요합니다.')
        if self.event_start and self.event_end and self.event_end < self.event_start:
            raise ValueError('종료일이 시작일보다 빠릅니다.')
        return self


# 같은 주제의 출처를 Fact에 연결하고 원문 위치·대조 메모를 남깁니다.
class EvidenceInput(Input):
    source_id: int = Field(gt=0)
    excerpt_reference: str = Field(min_length=2, max_length=500)
    evidence_note: str = Field(min_length=2, max_length=4000)


# 원문 직접 대조 확인과 사람의 검증 의견을 받습니다.
class VerifyInput(Input):
    editor_confirmed: Literal[True]
    verification_note: str = Field(min_length=3, max_length=4000)


# 이견·만료·반려 등 검증 완료 외의 상태로 바꾸는 사유입니다.
class FactStatusInput(Input):
    status: Literal['candidate', 'rejected', 'disputed', 'outdated']
    reason: str = Field(min_length=3, max_length=4000)


# 본문 문장 하나와 그 문장이 사용한 Fact Key 목록입니다.
class ClaimInput(Input):
    sentence: str = Field(min_length=2, max_length=1000)
    fact_keys: list[str] = Field(min_length=1, max_length=30)


# 제목도 근거 목록을 가지며 본문은 근거가 연결된 문장들의 배열로 받습니다.
class ArticleInput(Input):
    title: str = Field(min_length=5, max_length=200)
    title_fact_keys: list[str] = Field(min_length=1, max_length=30)
    claims: list[ClaimInput] = Field(min_length=1, max_length=20)


# 새 수정본 입력입니다. 해시로 사용자가 열어 본 기사 내용과 서버 내용을 비교합니다.
class EditInput(ArticleInput):
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    reason: str = Field(min_length=3, max_length=1000)


# 문장 한 개의 근거 일치·불일치 판정입니다. 사람이 원자료를 확인해야 저장할 수 있습니다.
class ClaimReviewInput(Input):
    status: Literal['supported', 'contradicted']
    source_checked: Literal[True]
    note: str = Field(min_length=3, max_length=800)
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


# 최종 승인 때 수치·시점/지역·인과/과장·출처/권리를 모두 확인해야 합니다.
class ReviewChecks(Input):
    numbers: Literal[True]
    time_and_region: Literal[True]
    no_unfounded_causes: Literal[True]
    sources_and_rights: Literal[True]


# 검토 요청·수정 요청·반려·승인을 구분합니다. 최종 승인만 checks가 추가로 필요합니다.
class ReviewInput(Input):
    action: Literal['submitted', 'changes_requested', 'rejected', 'approved']
    reason: str = Field(min_length=3, max_length=2000)
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    checks: ReviewChecks | None = None


# PUBLISH라는 명시적 확인과 기사 해시가 있어야 게시를 요청할 수 있습니다.
class PublishInput(Input):
    confirmation: Literal['PUBLISH']
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


# 게시 중단처럼 이유를 남겨야 하는 작업의 공통 입력입니다.
class ReasonInput(Input):
    reason: str = Field(min_length=3, max_length=2000)


# 파일 내용은 서버의 CSV/JSON 파서에서 행별 SourceInput·FactInput으로 다시 검사합니다.
class ImportInput(Input):
    format: Literal['csv', 'json']
    content: str = Field(min_length=2, max_length=180000)
