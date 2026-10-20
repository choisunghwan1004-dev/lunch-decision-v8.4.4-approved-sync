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
import json

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
    publication_frames = []
    review_frames = []
    # 선택한 경우에만 공개할 GIF를 만듭니다. 테스트 AI 응답이라는 표시는 모든 프레임에 남깁니다.
    def capture_publication(page, label, frames=None):
        if os.getenv('NEWS_RECORD_PUBLICATION') != '1':
            return
        from io import BytesIO
        from PIL import Image, ImageDraw, ImageFont
        font = os.environ['NEWS_DEMO_FONT']
        shot = Image.open(BytesIO(page.screenshot(type='jpeg', quality=88))).convert('RGB')
        canvas = Image.new('RGB', (shot.width, shot.height + 70), '#102335')
        canvas.paste(shot, (0, 70))
        draw = ImageDraw.Draw(canvas)
        draw.text((20, 8), label, font=ImageFont.truetype(font, 24), fill='white')
        draw.text((20, 40), '격리 MySQL 테스트 · 모의 AI 응답 · 실제 OpenAI 호출·운영 게시 없음', font=ImageFont.truetype(font, 17), fill='#b7d9eb')
        (publication_frames if frames is None else frames).append(canvas.quantize(colors=160))
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
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
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
            dialog.locator('[name=fact_type]').select_option('date_range')
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
            # 이미 열린 메인도 Fact 검증·수정 알림을 받아 다시 조회해야 합니다. AI는 아직 호출하지 않습니다.
            public_page = context.new_page()
            public_page.on('pageerror', lambda error: errors.append(str(error)))
            public_page.goto(base + '/')
            expect(public_page.locator('#regionalNews h2')).to_have_text('지역 소식')
            expect(public_page.locator('#regionalNews')).to_have_attribute('data-news-view', 'location-news-v1')
            expect(public_page.locator('[data-news-mode]')).to_have_count(0)
            expect(public_page.locator('#regionalNewsStatus')).to_contain_text('검증된 지역 소식이 아직 없습니다')
            # 선택한 시군구의 뉴스만 조회합니다. 화면 가상 ID가 아닌 숨은 실제 PK를 사용합니다.
            public_page.locator('#countryId').select_option(label='일본')
            public_page.locator('#provinceId').select_option(label='도쿄도')
            public_page.locator('#districtId').select_option(label='신주쿠구')
            expect(public_page.locator('#regionalNewsRegion')).to_contain_text('신주쿠구')
            expect(public_page.locator('#regionalNewsStatus')).to_contain_text('검증된 지역 소식이 아직 없습니다')
            japan_district = public_page.locator('#cityId').input_value()
            assert 0 < int(japan_district) < 1000000  # 가상 지역 ID는 다른 범위를 사용합니다.
            # 실제 HTTP까지 확인하므로 파일 검사만 통과한 오래된 서버를 놓치지 않습니다.
            subprocess.run(['node', 'scripts/news-ui-doctor.js'], cwd=ROOT, env=env, check=True)
            expect(page.get_by_role('button', name='상태 변경', exact=True)).to_have_count(0)
            for asset in ('/', '/admin', '/news-public.js', '/news-admin.js'):
                assert public_page.request.get(base + asset).headers['cache-control'] == 'no-store'
            public_page.locator('#regionalNews').scroll_into_view_if_needed()
            capture_publication(public_page, '지역 소식 1/8 · 검증 전 Fact 후보는 공개하지 않습니다')
            page.get_by_role('button', name='원문 대조', exact=True).click()
            dialog = page.locator('dialog:visible')
            dialog.locator('[name=editor_confirmed]').check()
            dialog.locator('[name=verification_note]').fill('원자료 날짜 및 지역 대조 완료')
            dialog.get_by_role('button', name='Fact 검증 완료', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(page.locator('#newsWorkspace')).to_contain_text('AI 기사 생성은 선택')
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('신주쿠 행사 소식')
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('원문 검증 소식')
            expect(public_page.locator('#regionalNewsCards .news-event-date')).to_have_text('행사일정 · 2026.11.01')
            public_page.locator('#regionalNews').scroll_into_view_if_needed()
            capture_publication(public_page, '지역 소식 2/8 · AI 생성 없이 검증 Fact·행사일정이 선택한 지역에 반영됩니다')
            public_page.get_by_role('button', name='소식 읽기 ↗').click()
            expect(public_page.locator('dialog:visible')).to_contain_text('브라우저 테스트 원자료')
            expect(public_page.locator('dialog:visible .news-event-list')).to_contain_text('2026.11.01')
            capture_publication(public_page, '지역 소식 3/8 · 검증된 사실과 원문 출처 확인')
            public_page.locator('dialog:visible').get_by_role('button', name='닫기', exact=True).click()
            # Fact를 수정하면 후보로 돌아가므로 열린 메인에서도 빠집니다. 빈 메모 재검증도 확인합니다.
            page.locator('[data-news-action="fact"][data-id]').click()
            page.locator('dialog:visible').get_by_role('button', name='Fact 저장', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(public_page.locator('#regionalNewsCards article')).to_have_count(0)
            page.get_by_role('button', name='원문 대조', exact=True).click()
            page.locator('dialog:visible [name=editor_confirmed]').check()
            page.locator('dialog:visible').get_by_role('button', name='Fact 검증 완료', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('원문 검증 소식')
            # 이전 Python 서버와 새 화면이 섞였을 때 빈 목록으로 숨기지 않고 재시작 방법을 안내합니다.
            feed = '**/api/news/public/feed?district_id=*&limit=30'
            public_page.route(feed, lambda route: route.fulfill(status=422, json={'detail': []}))
            public_page.locator('#regionalNewsRefresh').click()
            expect(public_page.locator('#regionalNewsStatus')).to_contain_text('Node·FastAPI를 모두 다시 시작')
            public_page.unroute(feed)
            public_page.locator('#regionalNewsRefresh').click()
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('원문 검증 소식')
            page.get_by_role('button', name='검증 Fact로 초안 생성').click()
            # 원문/기사 배치를 유지하고, 사람이 직접 체크할 네 포인트와 유료 AI 버튼을 제공합니다.
            dialog = page.locator('dialog:visible')
            expect(dialog).to_contain_text('원문 근거')
            expect(dialog).to_contain_text('검증할 기사')
            expect(dialog.locator('[data-human-check]')).to_have_count(4)
            expect(dialog.locator('[data-check], [data-review], [data-publish]')).to_have_count(0)
            expect(dialog.locator('[data-ai-review]')).to_be_disabled()  # 키 없는 운영 상태
            dialog.get_by_role('button', name='검증 완료·저장', exact=True).click()
            expect(dialog.locator('.news-error')).to_contain_text('사람 검수 항목 4개')
            dialog.locator('[data-human-check]').first.check()
            expect(dialog.locator('[data-human-progress]')).to_have_text('직접 확인 1/4')
            dialog.get_by_role('button', name='검증 완료·저장', exact=True).click()
            expect(dialog.locator('.news-error')).to_contain_text('사람 검수 항목 4개')
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('원문 검증 소식')
            # API 키 상태만 대역으로 표시합니다. Python 진입점도 격리 DB 전용 검수 대역입니다.
            dialog.get_by_role('button', name='닫기', exact=True).click()
            page.route('**/api/news/ai/status', lambda route: route.fulfill(json={'ok':True,'model':'gpt-6-luna','key_configured':True,'model_configured':True}))
            page.get_by_role('button', name='원문 비교·검증', exact=True).first.click()
            dialog = page.locator('dialog:visible')
            expect(dialog.locator('[data-human-check]:checked')).to_have_count(0)
            dialog.locator('.news-review-point details').first.locator('summary').click()
            expect(dialog).to_contain_text('20%')
            dialog.locator('.news-human-review').scroll_into_view_if_needed()
            capture_publication(page, '검수 1/4 · 잘못된 표현과 수정 예시를 보고 사람이 직접 확인', review_frames)
            dialog.locator('[data-ai-review]').click()
            expect(dialog.locator('[data-ai-review-result]')).to_contain_text('모의 AI 검수')
            expect(dialog.locator('[data-ai-review-result]')).to_contain_text('사람 확인 필요')
            expect(dialog.locator('[data-human-check]:checked')).to_have_count(0)
            dialog.locator('[data-ai-review-result]').scroll_into_view_if_needed()
            capture_publication(page, '검수 2/4 · AI 참고 결과는 사람 체크와 승인 상태를 바꾸지 않습니다', review_frames)
            # 재열어도 MySQL에 저장한 결과를 읽으며, 승인·문장 상태는 그대로 미검토입니다.
            draft_id = page.locator('#newsWorkspace [data-news-action=draft]').first.get_attribute('data-id')
            detail = page.request.get(base + '/api/news/drafts/' + str(draft_id)).json()
            assert detail['status']=='generated' and all(c['status']=='unverified' for c in detail['claims'])
            assert detail['ai_review']['state']=='completed' and detail['ai_review']['current']
            # 화면의 429 안내도 별도 응답 대역으로 확인합니다. 재클릭 성공은 DB의 완료 결과를 재사용합니다.
            ai_path = '**/api/news/drafts/*/ai-review'
            page.route(ai_path, lambda route: route.fulfill(status=429,json={'detail':'API 잔액 또는 예산이 부족합니다. 자동 재시도하지 않았습니다.'}))
            dialog.locator('[data-ai-review]').click()
            expect(dialog.locator('[data-ai-review-result]')).to_contain_text('잔액')
            expect(dialog.locator('[data-human-check]:checked')).to_have_count(0)
            page.unroute(ai_path)
            dialog.locator('[data-ai-review]').click()
            expect(dialog.locator('[data-ai-review-result]')).to_contain_text('모의 AI 검수')
            for box in dialog.locator('[data-human-check]').all():
                box.check()
            expect(dialog.locator('[data-human-progress]')).to_have_text('직접 확인 4/4')
            expect(dialog.locator('.news-error')).to_have_text('')
            expect(dialog.locator('[name=note]')).to_have_value('')
            dialog.locator('[type=submit]').scroll_into_view_if_needed()
            capture_publication(page, '검수 3/4 · 사람 검수 네 항목 확인 후 검증 완료 저장', review_frames)
            capture_publication(page, '지역 소식 4/8 · AI 참고 검수와 사람 네 포인트를 확인해 저장')
            dialog.get_by_role('button', name='검증 완료·저장', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(page.locator('#newsWorkspace')).to_contain_text('검증·저장 완료')
            expect(page.locator('#newsWorkspace')).to_contain_text('검증 저장 1건')
            expect(page.get_by_role('button', name='상태 변경', exact=True)).to_have_count(0)
            page.locator('[aria-label="메인 노출 상태"]').scroll_into_view_if_needed()
            capture_publication(page, '지역 소식 5/8 · 기사 검증·공개 저장, 상태 변경 항목 없음')
            capture_publication(page, '검수 4/4 · 사람 검수 기록과 검증 저장 결과 확인', review_frames)
            page.unroute('**/api/news/ai/status')
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('신주쿠 지역 소식 안내')
            expect(public_page.locator('#regionalNewsCards article')).to_have_count(1)
            expect(public_page.locator('#regionalNewsCards')).not_to_contain_text('원문 검증 소식')
            public_page.locator('#regionalNews').scroll_into_view_if_needed()
            capture_publication(public_page, '지역 소식 6/8 · 저장한 기사가 Fact 카드를 대신해 표시됩니다')
            # 여행 선택은 독립적입니다. 뉴스는 메인의 시군구 선택을 따라갑니다.
            public_page.locator('#travelCity').select_option(label='종로구')
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('신주쿠 지역 소식 안내')
            # 일본의 느린 재조회 응답을 잡고 한국으로 바꾼 뒤 반환하여 이전 응답 무시를 확인합니다.
            jp_feed = public_page.request.get(base + f'/api/news/public/feed?district_id={japan_district}&limit=30').json()
            held_feed = []
            held_path = f'**/api/news/public/feed?district_id={japan_district}&limit=30'
            public_page.route(held_path, lambda route: held_feed.append(route))
            with public_page.expect_request(lambda req: '/public/feed?district_id=' + japan_district in req.url):
                public_page.locator('#regionalNewsRefresh').click()
            public_page.locator('#countryId').select_option(label='대한민국')
            expect(public_page.locator('#regionalNewsCards article')).to_have_count(0)
            public_page.locator('#provinceId').select_option(label='서울특별시')
            public_page.locator('#districtId').select_option(label='종로구')
            expect(public_page.locator('#regionalNewsStatus')).to_contain_text('종로구의 검증된 지역 소식이 아직 없습니다')
            assert held_feed
            for held_request in held_feed:
                held_request.fulfill(json=jp_feed)
            expect(public_page.locator('#regionalNewsCards article')).to_have_count(0)
            public_page.unroute(held_path)
            public_page.locator('#regionalNews').scroll_into_view_if_needed()
            capture_publication(public_page, '지역 소식 7/8 · 종로구 선택 시 다른 지역 기사는 표시하지 않습니다')
            public_page.locator('#countryId').select_option(label='일본')
            public_page.locator('#provinceId').select_option(label='도쿄도')
            public_page.locator('#districtId').select_option(label='신주쿠구')
            expect(public_page.locator('#regionalNewsCards')).to_contain_text('신주쿠 지역 소식 안내')
            public_page.get_by_role('button', name='소식 읽기 ↗').click()
            expect(public_page.locator('dialog:visible')).to_contain_text('브라우저 테스트 원자료')
            expect(public_page.locator('dialog:visible .news-event-list')).to_contain_text('2026.11.01')
            capture_publication(public_page, '지역 소식 8/8 · 선택한 신주쿠구의 기사·행사일정·출처 확인')
            public_page.locator('dialog:visible').get_by_role('button', name='닫기', exact=True).click()
            page.get_by_role('button', name='원문 비교·검증', exact=True).first.click()
            page.locator('dialog:visible [data-stop-public]').click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(public_page.locator('#regionalNewsCards').get_by_role('button')).to_have_count(0)
            page.get_by_role('button', name='원문 비교·검증', exact=True).first.click()
            dialog = page.locator('dialog:visible')
            expect(dialog.locator('[data-human-check]')).to_have_count(4)
            for box in dialog.locator('[data-human-check]').all():
                box.check()
            dialog.get_by_role('button', name='검증 완료·저장', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            public_page.close()
            # 관리자 링크의 실제 지역 PK가 메인 선택을 복원하는지 확인합니다.
            href = page.get_by_role('link', name='이 지역 소식 확인 ↗').get_attribute('href')
            assert href == f'/?news_district_id={japan_district}#regionalNews'
            page.goto(base + href)
            expect(page.locator('#regionalNewsRegion')).to_contain_text('신주쿠구')
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
            if publication_frames:
                file = ROOT / 'docs/assets/news-publication-demo.gif'
                publication_frames[0].save(file, save_all=True, append_images=publication_frames[1:], duration=2800, loop=0, optimize=True, disposal=2)
                manifest_file = ROOT / 'docs/assets/demo-recordings.json'
                manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
                entry = {'file': 'docs/assets/news-publication-demo.gif',
                         'title': '지역 소식 — 선택한 시군구의 뉴스·행사일정과 검수',
                         'recorded_at': '2026-10-20',
                         'description': '격리 MySQL에서 **선택한 시군구의 검증 Fact·행사일정**을 조회하고, **모의 AI 기사**의 참고 검수·사람 4포인트·빈 메모 저장을 확인했습니다. 한국·일본 전환과 늦은 응답 무시, 관리자 상태 변경 항목 제거, 버전 진단, 공개 중단을 시험했습니다. **실제 OpenAI 호출이나 운영 기사 게시가 아닙니다.**',
                         'alt': '실제 테스트 화면에서 Fact 검증만으로 지역 소식 표시 후 모의 AI 기사의 검증 저장·시군구 전환·행사일정·출처를 확인한 여덟 단계'}
                manifest['recordings'] = [r for r in manifest['recordings'] if r['file'] != entry['file']] + [entry]
                manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                print(f'Publication GIF: {len(publication_frames)} frames, {file.stat().st_size} bytes', flush=True)
            if review_frames:
                file = ROOT / 'docs/assets/news-ai-review-demo.gif'
                review_frames[0].save(file, save_all=True, append_images=review_frames[1:], duration=3000, loop=0, optimize=True, disposal=2)
                manifest_file = ROOT / 'docs/assets/demo-recordings.json'
                manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
                entry = {'file':'docs/assets/news-ai-review-demo.gif', 'title':'ChatGPT 참고 검수와 사람 검수 포인트',
                         'recorded_at':'2026-10-20',
                         'description':'격리 MySQL·실제 브라우저에서 **검수 예시 → 모의 AI 대조 결과 → 사람 4개 직접 체크 → 저장**을 확인했습니다. AI가 사람 체크·승인을 자동 처리하지 않으며, 키 미설정·429 안내·결과 재사용도 시험했습니다. **유료 OpenAI 호출·운영 게시가 아닙니다.**',
                         'alt':'네 가지 검수 예시와 AI 참고 결과를 읽고 사람이 직접 체크해 저장하는 실제 테스트 화면 네 단계'}
                manifest['recordings']=[r for r in manifest['recordings'] if r['file']!=entry['file']]+[entry]
                manifest_file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(f'AI review GIF: {len(review_frames)} frames, {file.stat().st_size} bytes',flush=True)
            browser.close()
        print('Browser PASS: connection recovery + KR/JP topics/race + verified Facts without AI + edit/reverify refresh + stale server error/cache + AI assisted review/human four checks/blank memo + one card per topic + stop without Fact fallback + district filter/race + event dates + version doctor + Japan/mobile')
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
