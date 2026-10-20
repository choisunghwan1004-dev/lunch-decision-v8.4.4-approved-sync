import re
import sys

import pytest

from news_service.db import connect
from news_service import setup


def test_old_database_is_never_used(monkeypatch):
    monkeypatch.setenv('V83_DB_NAME', 'lunch_decision')
    monkeypatch.setenv('OLD_DB_NAME', 'lunch_decision')
    with pytest.raises(RuntimeError, match='다른 DB'):
        connect()


def test_env_initialization_preserves_settings_and_does_not_print_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    path = tmp_path / '.env'
    path.write_text('DB_PASSWORD=test-marker-password\nOPENAI_API_KEY=test-marker-key\nOPENAI_NEWS_MODEL=gpt-4.1-mini\nNEWS_INTERNAL_TOKEN=\n', encoding='utf-8')
    setup.initialize_env()
    first = path.read_text(encoding='utf-8')
    setup.initialize_env()
    assert path.read_text(encoding='utf-8') == first
    assert 'DB_PASSWORD=test-marker-password' in first and 'OPENAI_API_KEY=test-marker-key' in first
    token = re.search(r'^NEWS_INTERNAL_TOKEN=(.*)$', first, re.M).group(1)
    assert re.fullmatch('[0-9a-f]{64}', token)
    output = capsys.readouterr().out
    assert token not in output and 'test-marker' not in output
    assert 'OPENAI_NEWS_MODEL=gpt-4.1-mini' in first  # never silently change an existing setting


@pytest.mark.parametrize('line', ['NEWS_INTERNAL_TOKEN="{token}"', "NEWS_INTERNAL_TOKEN = '{token}'", 'export NEWS_INTERNAL_TOKEN={token}'])
def test_quoted_token_is_never_rotated_by_startup(tmp_path, monkeypatch, line):
    from dotenv import dotenv_values
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    token = 'a' * 64
    path = tmp_path / '.env'
    path.write_text('DB_PASSWORD=keep-secret\nOPENAI_API_KEY=keep-api\n' + line.format(token=token) + '\n')
    setup.initialize_env()
    first = path.read_bytes()
    setup.initialize_env()
    assert path.read_bytes() == first
    assert dotenv_values(path)['NEWS_INTERNAL_TOKEN'] == token
    assert dotenv_values(path)['DB_PASSWORD'] == 'keep-secret'
    assert dotenv_values(path)['OPENAI_API_KEY'] == 'keep-api'


def test_startup_env_only_needs_no_mysql_or_api(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    (tmp_path / '.env').write_text('DB_PASSWORD=keep-secret\nNEWS_INTERNAL_TOKEN=\n')
    monkeypatch.setattr(setup, 'connect', lambda: pytest.fail('설정 준비만 할 때 DB 연결 금지'))
    monkeypatch.setattr('dotenv.load_dotenv', lambda *args, **kwargs: True)
    monkeypatch.setattr(sys, 'argv', ['setup', '--init-env-only'])
    setup.main()
    assert re.search(r'NEWS_INTERNAL_TOKEN=[a-f0-9]{64}', (tmp_path / '.env').read_text())
