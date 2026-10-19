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


def wait_url(url):
    for _ in range(150):
        try:
            with urllib.request.urlopen(url, timeout=1):
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
            processes.append(subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT))
        base = f'http://127.0.0.1:{web_port}'
        wait_url(base + '/health')
        wait_url(base + '/api/news/public')
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
            expect(page.locator('#newsStatus')).to_contain_text('뉴스 서버 연결됨')
            page.get_by_role('button', name='새 주제', exact=True).click()
            dialog = page.locator('dialog:visible')
            options = dialog.locator('select[name=district_id] option').all_text_contents()
            japan_label = next(label for label in options if '신주쿠구' in label)
            dialog.locator('[name=district_id]').select_option(label=japan_label)
            dialog.locator('[name=title]').fill('신주쿠 행사 소식')
            dialog.get_by_role('button', name='주제 저장').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
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
        print('Browser PASS: admin source/fact/evidence/AI/review/approval/publish + Japan lunch/travel news + mobile')
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
