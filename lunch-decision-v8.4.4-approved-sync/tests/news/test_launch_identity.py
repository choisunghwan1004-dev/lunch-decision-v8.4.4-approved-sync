"""DB·AI 호출 없이 실행 폴더 지문이 버전 응답에 추가되는지 확인합니다."""
import hashlib
import os
from pathlib import Path
from news_service import app


def test_launch_identity_preserves_release_and_hides_actual_path(newsroom):
    client, _ = newsroom
    response = client.get('/public/version', headers={'x-news-internal-token': 'a' * 64})
    assert response.status_code == 200
    value = response.json()
    canonical = os.path.realpath(str(Path(app.__file__).resolve().parents[1]))
    if os.name == 'nt':
        canonical = canonical.replace('\\', '/').lower()
    assert value['project_root_id'] == hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    assert value['launcher_protocol'] == 'oneclick-v1'
    assert all(value[key] == original for key, original in app.RELEASE.items())
    assert canonical not in response.text
