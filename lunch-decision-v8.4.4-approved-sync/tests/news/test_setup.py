import re

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
