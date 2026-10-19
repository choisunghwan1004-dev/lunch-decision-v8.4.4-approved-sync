from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class TopicInput(Input):
    district_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=200)
    category: Literal['festival', 'tourism', 'transport', 'culture', 'other'] = 'tourism'
    is_demo: bool = False


class SourceInput(Input):
    source_kind: Literal['official', 'public_api', 'csv', 'manual', 'other'] = 'official'
    organization: str = Field(min_length=1, max_length=200)
    source_title: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=8, max_length=1024)
    published_at: datetime
    source_excerpt: str = Field(min_length=10, max_length=16000)
    license_note: str = Field(min_length=1, max_length=500)

    @field_validator('published_at')
    @classmethod
    def utc_date(cls, value):
        if value.tzinfo:
            from datetime import timezone
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class FactInput(Input):
    fact_key: str = Field(pattern=r'^[A-Za-z0-9_-]{2,80}$')
    fact_type: Literal['text', 'date', 'date_range', 'number', 'price', 'place', 'time']
    value_text: str = Field(min_length=1, max_length=4000)
    value_number: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    unit: str | None = Field(default=None, max_length=30)
    event_start: date | None = None
    event_end: date | None = None

    @model_validator(mode='after')
    def valid_fact(self):
        if self.fact_type in ('number', 'price') and self.value_number is None:
            raise ValueError('수치 Fact에는 수치 값이 필요합니다.')
        if self.event_start and self.event_end and self.event_end < self.event_start:
            raise ValueError('종료일이 시작일보다 빠릅니다.')
        return self


class EvidenceInput(Input):
    source_id: int = Field(gt=0)
    excerpt_reference: str = Field(min_length=2, max_length=500)
    evidence_note: str = Field(min_length=2, max_length=4000)


class VerifyInput(Input):
    editor_confirmed: Literal[True]
    verification_note: str = Field(min_length=3, max_length=4000)


class FactStatusInput(Input):
    status: Literal['candidate', 'rejected', 'disputed', 'outdated']
    reason: str = Field(min_length=3, max_length=4000)


class ClaimInput(Input):
    sentence: str = Field(min_length=2, max_length=1000)
    fact_keys: list[str] = Field(min_length=1, max_length=30)


class ArticleInput(Input):
    title: str = Field(min_length=5, max_length=200)
    title_fact_keys: list[str] = Field(min_length=1, max_length=30)
    claims: list[ClaimInput] = Field(min_length=1, max_length=20)


class EditInput(ArticleInput):
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    reason: str = Field(min_length=3, max_length=1000)


class ClaimReviewInput(Input):
    status: Literal['supported', 'contradicted']
    source_checked: Literal[True]
    note: str = Field(min_length=3, max_length=800)
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class ReviewChecks(Input):
    numbers: Literal[True]
    time_and_region: Literal[True]
    no_unfounded_causes: Literal[True]
    sources_and_rights: Literal[True]


class ReviewInput(Input):
    action: Literal['submitted', 'changes_requested', 'rejected', 'approved']
    reason: str = Field(min_length=3, max_length=2000)
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    checks: ReviewChecks | None = None


class PublishInput(Input):
    confirmation: Literal['PUBLISH']
    expected_content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class ReasonInput(Input):
    reason: str = Field(min_length=3, max_length=2000)
