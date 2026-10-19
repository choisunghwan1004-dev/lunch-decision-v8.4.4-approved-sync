"""키 설정과 실제 호출 점검. MySQL·Node 서버 없이도 Python만으로 실행합니다."""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import warnings

from .ai_runtime import MODEL, ROOT, NewsAIError, configuration, validate_configuration
from .article_ai import generate_article


def save_settings(settings, root=ROOT):
    """키·예약 설정을 교체하되 기존 DB·관리자 설정은 보존합니다."""
    path = root / '.env'
    source = path if path.exists() else root / '.env.example'
    original = source.read_text(encoding='utf-8-sig') if source.exists() else ''
    # 중복된 설정이 남으면 Node/Python의 해석이 달라질 수 있어 대상 항목을 모두 치웁니다.
    names = '|'.join(re.escape(name) for name in settings)
    lines = [line for line in original.splitlines()
             if not re.match(r'^\s*(?:export\s+)?(?:' + names + r')\s*=', line)]
    content = '\n'.join([*lines, *[name + '=' + json.dumps(str(value), ensure_ascii=False)
                                 for name, value in settings.items()], ''])
    temporary = None
    try:
        # 임시 파일도 키를 포함하므로 같은 폴더·비공개 권한으로 만들고 항상 정리합니다.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         prefix='.openai-env-', suffix='.tmp', dir=root, delete=False) as out:
            temporary = Path(out.name)
            out.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def save_key(key, root=ROOT):
    if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,}', key):
        raise ValueError('sk-로 시작하는 API 키를 공백·줄바꿈 없이 입력하세요.')
    return save_settings({'OPENAI_NEWS_MODEL': MODEL, 'OPENAI_API_KEY': key}, root)


def configure_key():
    print('OpenAI API Keys: https://platform.openai.com/api-keys')
    print('입력은 화면에 표시하지 않습니다. 키는 이 PC의 프로젝트 .env에만 저장합니다.')
    # 터미널이 숨김 입력을 지원하지 않으면 평문 입력으로 전환하지 않고 중단합니다.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            key = getpass.getpass('OpenAI API 키 입력: ').strip()
    except (getpass.GetPassWarning, EOFError):
        print('숨김 입력을 지원하는 PowerShell에서 실행하거나 프로젝트 .env를 직접 편집하세요.')
        return 1
    if not key:
        print('입력이 없어 설정을 변경하지 않았습니다.')
        return 1
    save_key(key)
    print('키와 OPENAI_NEWS_MODEL=gpt-6-luna를 저장했습니다. DB·관리자 설정은 보존했습니다.')
    print('실행 중인 FastAPI를 종료 후 다시 시작하세요. 14_OpenAI_실제호출테스트.bat으로 확인할 수 있습니다.')
    return 0


def live_check():
    """운영 기사와 같은 생성기로 가상 Fact 1건을 한 번 전송합니다. DB 저장·게시는 없습니다."""
    validate_configuration()
    topic = {'region_name': '수업용 가상 지역', 'title': '수업용 가상 자료 연결 점검',
             'category': 'other', 'is_demo': True}
    facts = [{'id': 1, 'fact_key': 'DEMO_COUNT', 'fact_type': 'number',
              'value_text': '수업용 가상 자료의 참가자는 10명입니다.', 'value_number': 10, 'unit': '명',
              'verification_note': '연결 검사 전용 고정 가상 값입니다. 실제 기사 자료가 아닙니다.'}]
    started = time.monotonic()
    article, usage = generate_article(topic, facts)
    return {'ok': True, 'live_openai_succeeded': True, 'is_demo': True,
            'model': MODEL, 'elapsed_seconds': round(time.monotonic() - started, 2),
            'article': article, 'usage': usage,
            'message': '실제 API 응답의 JSON·Fact 연결 형식 확인 완료. 미검토 시연 초안이며 DB 저장·게시는 하지 않았습니다.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='OpenAI 키 설정·무료 설정 확인·실제 유료 호출')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--configure-key', action='store_true', help='화면에 표시하지 않고 로컬 키 입력')
    mode.add_argument('--status', action='store_true', help='API를 호출하지 않는 무료 설정 확인')
    mode.add_argument('--live', action='store_true', help='가상 자료로 실제 API 한 번 호출 (비용 발생)')
    args = parser.parse_args(argv)
    try:
        if args.configure_key:
            return configure_key()
        if args.status:
            print(json.dumps(configuration(), ensure_ascii=False, indent=2))
            return 0
        print('gpt-6-luna 실제 호출을 한 번 실행합니다. API 비용이 발생할 수 있습니다. 자동 재시도하지 않습니다.', flush=True)
        result = live_check()
    except NewsAIError as error:
        result = {'ok': False, 'live_openai_succeeded': False, 'model': MODEL,
                  'code': error.code, 'message': error.message}
    except (ValueError, OSError):
        # 알 수 없는 예외 전문은 키·DB 정보가 섞일 수 있으므로 파일과 화면에 출력하지 않습니다.
        print('설정 또는 파일 처리에 실패했습니다. .env 입력 형식과 폴더 쓰기 권한을 확인하세요.')
        return 1
    result['checked_at'] = datetime.now(timezone.utc).isoformat()
    folder = ROOT / 'test-results'
    try:
        folder.mkdir(exist_ok=True)
        (folder / 'openai-live.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except OSError:
        print('결과 파일을 저장하지 못했습니다. 폴더 쓰기 권한을 확인하세요.')
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('결과: test-results/openai-live.json')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    # Windows 콘솔에서도 한글 결과 파일과 화면을 같은 인코딩으로 읽습니다.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
