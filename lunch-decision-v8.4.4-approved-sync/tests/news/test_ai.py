import json
from types import SimpleNamespace

import pytest
from news_service.article_ai import MODEL, generate_article
from news_service.validation import parse_draft

ARTICLE = {'title': '검증된 지역 행사 안내', 'title_fact_keys': ['F01'], 'claims': [{'sentence': '행사가 개최됩니다.', 'fact_keys': ['F01']}]}


class Client:
    def __init__(self, raw=None, status='completed'):
        self.raw = raw or json.dumps(ARTICLE, ensure_ascii=False)
        self.status = status
        self.responses = self
        self.arguments = None

    def create(self, **kwargs):
        self.arguments = kwargs
        return SimpleNamespace(output_text=self.raw, status=self.status, id='response-test', usage=SimpleNamespace(input_tokens=120, output_tokens=40, input_tokens_details=SimpleNamespace(cached_tokens=5)))


def test_responses_structured_output_and_exact_model(monkeypatch):
    monkeypatch.setenv('OPENAI_NEWS_MODEL', MODEL)
    client = Client()
    article, usage = generate_article({'region_name': '서울', 'title': '행사', 'category': 'culture', 'is_demo': False}, [{'id': 1, 'fact_key': 'F01', 'value_text': '행사가 개최됩니다.'}], client)
    assert client.arguments['model'] == 'gpt-6-luna'
    assert client.arguments['text']['format']['strict'] is True
    assert client.arguments['reasoning'] == {'effort': 'none'}
    assert client.arguments['store'] is False
    assert article['body'] == '\n\n'.join(c['sentence'] for c in article['claims'])
    assert usage['cached_input_tokens'] == 5


@pytest.mark.parametrize('mutation', ['unknown', 'empty', 'separate_body', 'title_missing_evidence'])
def test_ai_output_cannot_bypass_sentence_evidence(mutation):
    data = json.loads(json.dumps(ARTICLE))
    if mutation == 'unknown':
        data['claims'][0]['fact_keys'] = ['UNKNOWN']
    elif mutation == 'empty':
        data['claims'] = []
    elif mutation == 'separate_body':
        data['body'] = '이 근거 없는 본문은 저장하면 안 됩니다.'
    else:
        data['title_fact_keys'] = []
    with pytest.raises(ValueError):
        parse_draft(data, {'F01'})


def test_truncated_output_is_rejected(monkeypatch):
    monkeypatch.setenv('OPENAI_NEWS_MODEL', MODEL)
    with pytest.raises(ValueError, match='완료되지'):
        generate_article({'region_name': '서울', 'title': '행사', 'category': 'culture', 'is_demo': False}, [], Client(status='incomplete'))


def test_old_model_configuration_cannot_silently_run(monkeypatch):
    monkeypatch.setenv('OPENAI_NEWS_MODEL', 'gpt-4.1-mini')
    with pytest.raises(ValueError, match='gpt-6-luna'):
        generate_article({}, [], Client())
