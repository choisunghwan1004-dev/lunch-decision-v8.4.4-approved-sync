"""Optional browser integration test: temporary MySQL DB + actual Node/FastAPI UI.
Requires dev dependencies, Playwright and Chromium; no paid OpenAI requests.
"""
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

import mysql.connector
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / 'test-results'


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_url(url, headers=None):
    for _ in range(150):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=1):
                return
        except Exception:
            time.sleep(.1)
    raise RuntimeError('Test server did not start: ' + url)


def main():
    name = 'news_test_ui_' + uuid.uuid4().hex[:10]
    admin = mysql.connector.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '3306')),
                                    user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''))
    cur = admin.cursor()
    processes, handles = [], []
    ARTIFACTS.mkdir(exist_ok=True)
    try:
        cur.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        cur.execute(f'USE `{name}`')
        for file in ('01_schema.sql', '02_v84_extensions.sql', '03_v844_google_sync.sql'):
            sql = re.sub(r'--[^\n]*', '', (ROOT / 'sql' / file).read_text(encoding='utf-8'))
            for statement in sql.split(';'):
                statement = statement.strip()
                if statement and not re.match(r'^(CREATE DATABASE|USE\s)', statement, re.I):
                    cur.execute(statement)
        admin.commit()
        from news_service.setup import migrate
        migrate(admin)
        web_port, api_port = port(), port()
        password = secrets.token_hex(18)
        env = {**os.environ, 'V83_DB_NAME': name, 'PORT': str(web_port), 'NEWS_BROWSER_TEST_RUN': '1',
               'NEWS_SERVICE_URL': f'http://127.0.0.1:{api_port}', 'NEWS_INTERNAL_TOKEN': secrets.token_hex(32),
               'OPENAI_NEWS_MODEL': 'gpt-6-luna', 'OPENAI_API_KEY': '', 'GOOGLE_MAPS_API_KEY': '', 'OPENWEATHER_API_KEY': '',
               'ADMIN_USERNAME': 'news-test-editor', 'ADMIN_PASSWORD': password, 'SESSION_SECRET': secrets.token_hex(32)}
        subprocess.run(['node', 'scripts/seed-demo.js'], cwd=ROOT, env=env, check=True, capture_output=True)
        subprocess.run(['node', 'scripts/seed-integration.js'], cwd=ROOT, env=env, check=True, capture_output=True)
        subprocess.run(['node', 'scripts/seed-travel-50.js'], cwd=ROOT, env=env, check=True, capture_output=True)
        for command, logfile in [([sys.executable, '-m', 'uvicorn', 'browser_app:app', '--app-dir', str(ROOT / 'tests' / 'news'), '--host', '127.0.0.1', '--port', str(api_port)], 'browser-api.log'), (['node', 'server.js'], 'browser-node.log')]:
            handle = (ARTIFACTS / logfile).open('w')
            handles.append(handle)
            # 처음에는 Node의 토큰 누락 상태로 사용자의 빈 선택 목록 오류를 실제 재현합니다.
            launch_env = {**env, 'NEWS_INTERNAL_TOKEN': ''} if command[0] == 'node' else env
            processes.append(subprocess.Popen(command, cwd=ROOT, env=launch_env, stdout=handle, stderr=subprocess.STDOUT))
        base = f'http://127.0.0.1:{web_port}'
        wait_url(base + '/health')
        wait_url(f'http://127.0.0.1:{api_port}/health', {'x-news-internal-token': env['NEWS_INTERNAL_TOKEN']})
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/admin')
            page.locator('#username').fill('news-test-editor')
            page.locator('#password').fill(password)
            page.get_by_role('button', name='관리자 로그인', exact=True).click()
            page.get_by_role('button', name='📰 지역 뉴스', exact=True).click()
            expect(page.locator('#newsStatus')).to_contain_text('18_뉴스_연결복구')
            expect(page.get_by_role('button', name='새 주제', exact=True)).to_be_disabled()
            expect(page.locator('#newsTopic')).to_be_disabled()
            expect(page.locator('#newsRecovery')).to_be_visible()
            # 실제 Node 프로세스를 올바른 설정으로 재시작합니다. 기존 세션은 다시 로그인합니다.
            processes[1].terminate();processes[1].wait(timeout=5)
            handle = (ARTIFACTS / 'browser-node-recovered.log').open('w')
            handles.append(handle)
            processes.append(subprocess.Popen(['node', 'server.js'], cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT))
            wait_url(base + '/health')
            page.reload()
            page.locator('#username').fill('news-test-editor')
            page.locator('#password').fill(password)
            page.get_by_role('button', name='관리자 로그인', exact=True).click()
            page.get_by_role('button', name='📰 지역 뉴스', exact=True).click()
            expect(page.locator('#newsStatus')).to_contain_text('뉴스 서버 연결됨')
            expect(page.locator('#newsRecovery')).to_be_hidden()
            expect(page.locator('#newsTopic')).to_be_disabled()
            expect(page.locator('#newsTopicHint')).to_contain_text('등록된 주제가 없습니다')
            # 지역 미등록과 연결 장애를 구분하고, 재조회하면 선택 기능을 복구합니다.
            page.route('**/api/news/regions', lambda route: route.fulfill(json=[]))
            page.get_by_role('button', name='연결 다시 확인', exact=True).click()
            expect(page.locator('#newsTopicHint')).to_contain_text('등록된 시군구가 없습니다')
            expect(page.get_by_role('button', name='새 주제', exact=True)).to_be_disabled()
            page.unroute('**/api/news/regions')
            page.get_by_role('button', name='연결 다시 확인', exact=True).click()
            expect(page.get_by_role('button', name='새 주제', exact=True)).to_be_enabled()
            # 키가 없을 때는 실제 호출 버튼을 막고 설정 방법을 안내합니다.
            page.get_by_role('button', name='OpenAI 연결 확인', exact=True).click()
            expect(page.locator('dialog:visible')).to_contain_text('키 미설정')
            expect(page.locator('dialog:visible [data-live-check]')).to_be_disabled()
            page.locator('dialog:visible').get_by_role('button', name='닫기', exact=True).click()
            # 화면 성공 표시는 명시적인 테스트 응답으로만 확인합니다. 유료 API는 호출하지 않습니다.
            page.route('**/api/news/ai/status', lambda route: route.fulfill(json={'ok': True, 'model': 'gpt-6-luna', 'key_configured': True, 'model_configured': True}))
            page.route('**/api/news/ai/check', lambda route: route.fulfill(json={'ok': True, 'message': '브라우저 테스트 대역 응답', 'model': 'gpt-6-luna', 'usage': {'request_id': 'mock-browser-only', 'input_tokens': 10, 'output_tokens': 5}, 'elapsed_seconds': 0.1, 'article': {'title': '수업용 가상 초안', 'body': '참가자는 10명입니다.'}}))
            page.get_by_role('button', name='OpenAI 연결 확인', exact=True).click()
            page.locator('dialog:visible [data-live-check]').click()
            expect(page.locator('dialog:visible [data-live-result]')).to_contain_text('mock-browser-only')
            page.locator('dialog:visible').get_by_role('button', name='닫기', exact=True).click()
            page.unroute('**/api/news/ai/status');page.unroute('**/api/news/ai/check')
            expect(page.locator('#newsStatus')).to_contain_text('뉴스 서버 연결됨')
            page.get_by_role('button', name='새 주제', exact=True).click()
            dialog = page.locator('dialog:visible')
            options = dialog.locator('select[name=district_id] option').all_text_contents()
            japan_label = next(label for label in options if '신주쿠구' in label)
            dialog.locator('[name=district_id]').select_option(label=japan_label)
            dialog.locator('[name=title]').fill('신주쿠 행사 소식')
            dialog.get_by_role('button', name='주제 저장').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            japan_topic = page.locator('#newsTopic').input_value()
            assert japan_topic
            expect(page.locator('#newsWorkspace')).to_contain_text('신주쿠 행사 소식')
            # 두 번째 한국 주제를 저장하고 실제 DB의 두 주제를 번갈아 선택합니다.
            page.get_by_role('button', name='새 주제', exact=True).click()
            dialog = page.locator('dialog:visible')
            labels = dialog.locator('select[name=district_id] option').all_text_contents()
            dialog.locator('[name=district_id]').select_option(label=next(label for label in labels if '종로구' in label))
            dialog.locator('[name=title]').fill('종로 관광 소식 선택 검사')
            dialog.get_by_role('button', name='주제 저장').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            korea_topic = page.locator('#newsTopic').input_value()
            assert korea_topic != japan_topic
            held = []
            path = '**/api/news/topics/' + japan_topic + '/sources'
            page.route(path, lambda route: held.append(route))
            page.locator('#newsTopic').select_option(japan_topic)
            page.wait_for_function('document.querySelector("#newsTopic").value === ' + repr(japan_topic))
            page.locator('#newsTopic').select_option(korea_topic)
            expect(page.locator('#newsWorkspace')).to_contain_text('종로 관광 소식 선택 검사')
            assert held, 'first topic request must be held'
            for request in held:
                request.fulfill(json=[])
            expect(page.locator('#newsWorkspace')).to_contain_text('종로 관광 소식 선택 검사')
            page.unroute(path)
            page.locator('#newsTopic').select_option(japan_topic)
            expect(page.locator('#newsWorkspace')).to_contain_text('신주쿠 행사 소식')
            page.get_by_role('button', name='출처 등록', exact=True).click()
            dialog = page.locator('dialog:visible')
            for key, value in {'organization': '브라우저 테스트 기관', 'source_title': '브라우저 테스트 원자료',
                               'source_url': 'https://example.org/browser-evidence', 'published_at': '2026-10-19T00:00',
                               'source_excerpt': '신주쿠구의 테스트 행사는 2026년 11월 1일 개최됩니다.',
                               'license_note': '브라우저 테스트용 자료'}.items():
                dialog.locator('[name=' + key + ']').fill(value)
            dialog.get_by_role('button', name='출처 저장').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            page.get_by_role('button', name='Fact 등록', exact=True).click()
            dialog = page.locator('dialog:visible')
            dialog.locator('[name=fact_key]').fill('EVENT_DATE')
            dialog.locator('[name=fact_type]').select_option('date')
            dialog.locator('[name=value_text]').fill('신주쿠구의 테스트 행사는 2026년 11월 1일 개최됩니다.')
            dialog.locator('[name=event_start]').fill('2026-11-01')
            dialog.get_by_role('button', name='Fact 저장').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            page.get_by_role('button', name='근거 연결', exact=True).click()
            dialog = page.locator('dialog:visible')
            dialog.locator('[name=excerpt_reference]').fill('본문 1문단')
            dialog.locator('[name=evidence_note]').fill('행사 일정 원문과 대조')
            dialog.get_by_role('button', name='연결 저장').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            page.get_by_role('button', name='원문 대조', exact=True).click()
            dialog = page.locator('dialog:visible')
            dialog.locator('[name=editor_confirmed]').check()
            dialog.locator('[name=verification_note]').fill('원자료 날짜 및 지역 대조 완료')
            dialog.get_by_role('button', name='Fact 검증 완료', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            page.get_by_role('button', name='검증 Fact로 초안 생성').click()
            expect(page.locator('dialog:visible [data-claim]')).to_have_count(2)
            for index in range(2):
                row = page.locator('dialog:visible [data-claim]').nth(index)
                row.locator('[data-source-checked]').check()
                row.locator('[data-claim-note]').fill('브라우저에서 원자료 직접 대조 완료')
                row.get_by_role('button', name='근거 일치', exact=True).click()
                expect(page.locator('dialog:visible [data-claim]').nth(index)).to_contain_text('근거 대조 완료')
            dialog = page.locator('dialog:visible')
            for field in ('numbers', 'time_and_region', 'no_unfounded_causes', 'sources_and_rights'):
                dialog.locator('[name=' + field + ']').check()
            dialog.locator('[name=review_reason]').fill('수치·시점·지역·출처 최종 확인')
            dialog.evaluate('(node)=>node.scrollTop=0')
            page.screenshot(path=str(ARTIFACTS / 'news-admin-desktop.png'))
            dialog.get_by_role('button', name='최종 승인', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            page.get_by_role('button', name='기사 검토·수정').first.click()
            page.locator('dialog:visible').get_by_role('button', name='승인본 게시').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(page.locator('#newsWorkspace')).to_contain_text('게시 중')
            page.goto(base + '/')
            page.locator('#countryId').select_option(label='일본')
            page.locator('#provinceId').select_option(label='도쿄도')
            page.locator('#districtId').select_option(label='신주쿠구')
            expect(page.locator('#regionalNewsCards')).to_contain_text('신주쿠 지역 소식 안내')
            page.get_by_role('button', name='소식 읽기 ↗').click()
            expect(page.locator('dialog:visible')).to_contain_text('브라우저 테스트 원자료')
            expect(page.locator('dialog:visible')).to_contain_text('2026년 11월 1일')
            page.locator('dialog:visible').get_by_role('button', name='닫기').click()
            page.get_by_role('button', name='여행 지역', exact=True).click()
            page.locator('#travelCity').select_option(label='신주쿠구')
            expect(page.locator('#regionalNewsCards')).to_contain_text('신주쿠 지역 소식 안내')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#regionalNews').scroll_into_view_if_needed()
            page.locator('#regionalNews').screenshot(path=str(ARTIFACTS / 'news-public-mobile.png'))
            width = page.locator('#regionalNews').evaluate('(node)=>({width:node.getBoundingClientRect().width,scroll:node.scrollWidth})')
            assert width['scroll'] <= width['width'] + 2, width
            page.goto(base + '/admin')
            page.get_by_role('button', name='📰 지역 뉴스', exact=True).click()
            expect(page.locator('#newsStatus')).to_contain_text('뉴스 서버 연결됨')
            page.get_by_role('button', name='새 주제', exact=True).click()
            dialog=page.locator('dialog:visible')
            dialog.locator('[name=district_id]').select_option(label=japan_label)
            dialog.locator('[name=title]').fill('CSV 수집 브라우저 테스트')
            dialog.locator('[name=is_demo]').check()
            dialog.get_by_role('button', name='주제 저장').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            page.get_by_role('button', name='CSV·JSON 가져오기').click()
            page.locator('dialog:visible input[type=file]').set_input_files(str(ROOT/'examples/news_demo.csv'))
            page.locator('dialog:visible').get_by_role('button', name='파일 가져오기').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(page.locator('#newsWorkspace')).to_contain_text('VISITOR_COUNT')
            expect(page.locator('#newsWorkspace')).to_contain_text('검증 대기')
            assert not errors, errors
            browser.close()
        print('Browser PASS: connection recovery + empty lists + KR/JP topic selection/race + source/fact/review/publish + Japan/mobile')
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        for handle in handles:
            handle.close()
        if name.startswith('news_test_ui_'):
            cur.execute(f'DROP DATABASE IF EXISTS `{name}`')
        cur.close()
        admin.close()


if __name__ == '__main__':
    main()
