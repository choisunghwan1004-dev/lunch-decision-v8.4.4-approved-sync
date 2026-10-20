"""실제 Node/FastAPI 화면을 임시 MySQL DB에서 조작하고 README용 GIF로 저장합니다.

운영 DB를 사용하지 않습니다. MySQL 접속 계정에는 임시 DB 생성·삭제 권한이 필요합니다.
실행: python scripts/record-readme-demo.py --font <한글 TTF 경로>
준비: requirements-dev.txt, Pillow, Playwright Chromium, npm ci, 실행 중인 MySQL.
"""
import argparse
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json
import os
import platform
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid

import mysql.connector
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / 'docs/assets'
RESULTS = ROOT / 'test-results/readme-demo'


def free_port():
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
    raise RuntimeError('테스트 서버 시작 실패: ' + url)


def choose(page, selector, label):
    """표시된 실제 옵션을 사용합니다. PC마다 달라지는 DB PK를 하드코딩하지 않습니다."""
    select = page.locator(selector)
    options = select.locator('option').all_text_contents()
    matches = [text for text in options if label in text]
    if not matches:
        raise RuntimeError(f'{selector}에 {label} 선택지가 없습니다: {options}')
    select.select_option(label=matches[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', required=True, type=Path, help='한글을 표시할 수 있는 TTF 파일')
    args = parser.parse_args()
    title_font = ImageFont.truetype(str(args.font), 22)
    note_font = ImageFont.truetype(str(args.font), 15)
    # 이름은 이 도구가 생성합니다. V83_DB_NAME으로 사용자의 운영 DB를 받지 않습니다.
    name = 'news_test_ui_' + uuid.uuid4().hex[:10]
    conn = mysql.connector.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '3306')),
                                   user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''))
    cur = conn.cursor()
    processes, handles = [], []
    ASSETS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    recordings, metrics = [], {}
    try:
        cur.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        cur.execute(f'USE `{name}`')
        for file in ('01_schema.sql', '02_v84_extensions.sql', '03_v844_google_sync.sql'):
            sql = re.sub(r'--[^\n]*', '', (ROOT / 'sql' / file).read_text(encoding='utf-8'))
            for statement in sql.split(';'):
                statement = statement.strip()
                if statement and not re.match(r'^(CREATE DATABASE|USE\s)', statement, re.I):
                    cur.execute(statement)
        conn.commit()
        from news_service.setup import migrate
        migrate(conn)
        # 실제 서버를 실행하지만 유료·외부 키와 자동 예약은 명시적으로 비웁니다.
        web_port, api_port = free_port(), free_port()
        password = secrets.token_hex(18)
        env = {**os.environ, 'V83_DB_NAME': name, 'OLD_DB_NAME': 'news_demo_original_never_used',
               'PORT': str(web_port), 'NEWS_SERVICE_URL': f'http://127.0.0.1:{api_port}',
               'NEWS_INTERNAL_TOKEN': secrets.token_hex(32), 'OPENAI_NEWS_MODEL': 'gpt-6-luna',
               'OPENAI_API_KEY': '', 'GOOGLE_MAPS_API_KEY': '', 'OPENWEATHER_API_KEY': '',
               'NEWS_AUTO_ENABLED': '0', 'NOTION_TOKEN': '', 'NOTION_API_KEY': '',
               'ADMIN_USERNAME': 'readme-test-editor', 'ADMIN_PASSWORD': password,
               'SESSION_SECRET': secrets.token_hex(32)}
        for script in ('seed-demo.js', 'seed-integration.js', 'seed-travel-50.js'):
            subprocess.run(['node', 'scripts/' + script], cwd=ROOT, env=env, check=True, capture_output=True)
        for command, file in [([sys.executable, '-m', 'uvicorn', 'news_service.app:app', '--host', '127.0.0.1', '--port', str(api_port)], 'api.log'),
                              (['node', 'server.js'], 'node.log')]:
            handle = (RESULTS / file).open('w', encoding='utf-8')
            handles.append(handle)
            processes.append(subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT))
        base = f'http://127.0.0.1:{web_port}'
        wait_url(base + '/health')
        wait_url(f'http://127.0.0.1:{api_port}/health', {'x-news-internal-token': env['NEWS_INTERNAL_TOKEN']})
        cur.execute('SELECT VERSION()')
        mysql_version = cur.fetchone()[0]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': 1200, 'height': 840}, locale='ko-KR', timezone_id='Asia/Seoul', reduced_motion='reduce')
            page = context.new_page()
            errors, external_requests = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            # 외부 서비스 요청은 어떤 것이든 차단하고 기록합니다. 응답을 꾸며 넣지 않습니다.
            def local_only(route):
                if urllib.parse.urlparse(route.request.url).hostname in ('127.0.0.1', 'localhost'):
                    route.continue_()
                else:
                    external_requests.append({'url': route.request.url, 'type': route.request.resource_type})
                    route.abort()
            context.route('**/*', local_only)

            def snap(frames, label, note='격리 테스트 DB · 가상 장소 · 외부 API 미호출', duration=2000):
                page.wait_for_timeout(220)
                shot = Image.open(BytesIO(page.screenshot(type='jpeg', quality=88))).convert('RGB')
                canvas = Image.new('RGB', (shot.width, shot.height + 68), '#102335')
                canvas.paste(shot, (0, 68))
                draw = ImageDraw.Draw(canvas)
                draw.text((20, 8), label, font=title_font, fill='white')
                draw.text((20, 38), note, font=note_font, fill='#b7d9eb')
                frames.append((canvas, duration))

            def save(frames, slug, title, description, alt):
                images = [img.quantize(colors=160) for img, _ in frames]
                file = ASSETS / (slug + '-demo.gif')
                images[0].save(file, save_all=True, append_images=images[1:],
                               duration=[d for _, d in frames], loop=0, optimize=True, disposal=2)
                recordings.append({'file': 'docs/assets/' + file.name, 'title': title,
                                   'description': description, 'alt': alt})
                metrics[slug] = {'frames': len(frames), 'bytes': file.stat().st_size, 'duration_ms': sum(d for _, d in frames)}
                print(f'{slug}: {len(frames)} frames, {file.stat().st_size} bytes', flush=True)

            # 1. 기존 점심 화면: 실제 선택 이벤트와 추천 API 응답을 사용합니다.
            page.goto(base)
            expect(page.locator('#systemStatus')).to_contain_text('DB 연결됨')
            expect(page.locator('#result .food-info')).to_be_visible()
            page.evaluate('document.fonts.ready')
            frames = []
            snap(frames, '점심 1/5 · 기존 사용자 메인과 DB 연결')
            page.locator('#profile').scroll_into_view_if_needed()
            for selector, label in [('#countryId', '대한민국'), ('#provinceId', '서울'), ('#districtId', '종로'), ('#townId', '종로'), ('#areaId', '종각')]:
                choose(page, selector, label)
            snap(frames, '점심 2/5 · 대한민국 → 서울 → 종로 → 상권 선택')
            page.locator('#budget').fill('15000')
            page.locator('#decide').click()
            expect(page.locator('#decide')).to_be_enabled()
            expect(page.locator('#result .food-info')).to_be_visible()
            page.locator('#recommendation').scroll_into_view_if_needed()
            snap(frames, '점심 3/5 · 예산을 반영한 추천 결과와 근거')
            for selector, label in [('#countryId', '일본'), ('#provinceId', '도쿄'), ('#districtId', '신주쿠'), ('#townId', '니시신주쿠'), ('#areaId', '신주쿠')]:
                choose(page, selector, label)
            page.locator('#profile').scroll_into_view_if_needed()
            snap(frames, '점심 4/5 · 일본 → 도쿄 → 신주쿠 지역도 선택')
            page.locator('#decide').click()
            expect(page.locator('#decide')).to_be_enabled()
            expect(page.locator('#result .food-info')).to_be_visible()
            page.locator('#recommendation').scroll_into_view_if_needed()
            expect(page.locator('#heroArea')).to_contain_text('신주쿠')
            snap(frames, '점심 5/5 · 일본 지역 추천 결과 확인', duration=2800)
            save(frames, 'lunch', '점심 추천 — 한국·일본 지역 선택과 결과',
                 '한국 종로구와 일본 신주쿠구를 실제 선택하고 추천 결과를 확인했습니다. 장소는 **가상 테스트 데이터**입니다.',
                 '한국과 일본 지역을 차례로 선택해 점심 추천을 확인한 실제 테스트 화면')

            # 2. 여행: 종로의 충분한 가상 장소로 2일 12단계를 생성합니다.
            frames = []
            choose(page, '#travelCity', '종로')
            page.locator('#travelDays').select_option('2')
            page.locator('#travelAI').scroll_into_view_if_needed()
            snap(frames, '여행 1/4 · 종로구와 2일 일정 선택')
            page.locator('#makeTrip').click()
            expect(page.locator('#tripResult .itinerary-day')).to_have_count(2)
            expect(page.locator('#tripResult .itinerary-stop')).to_have_count(12)
            snap(frames, '여행 2/4 · 서버가 2일·12단계 일정 생성')
            page.locator('.itinerary-day').first.scroll_into_view_if_needed()
            snap(frames, '여행 3/4 · 1일차 관광·점심·카페·관광·저녁·숙박')
            page.locator('.itinerary-day').nth(1).scroll_into_view_if_needed()
            snap(frames, '여행 4/4 · 2일차 장소와 이동시간 미확인 표시', duration=2800)
            save(frames, 'travel', '여행 일정 — 2일 일정과 날짜별 여섯 단계',
                 '종로구 2일 일정의 **12개 단계**를 확인했습니다. 가상 장소의 이동시간·영업정보는 확인하지 않은 상태로 표시됩니다.',
                 '종로구 2일 여행 일정을 생성하고 날짜별 여섯 단계를 확인한 실제 테스트 화면')

            # 3. 뉴스: 실제 FastAPI + MySQL로 CSV를 가져오며 AI·승인·게시를 실행하지 않습니다.
            page.goto(base + '/admin')
            page.locator('#username').fill('readme-test-editor')
            page.locator('#password').fill(password)
            page.get_by_role('button', name='관리자 로그인', exact=True).click()
            page.get_by_role('button', name='📰 지역 뉴스', exact=True).click()
            expect(page.locator('#newsStatus')).to_contain_text('뉴스 서버 연결됨')
            frames = []
            note = '격리 테스트 DB · 실제 공개 자료 · 검증 대기 · AI·게시 미실행'
            snap(frames, '지역 뉴스 1/7 · 뉴스 서버 연결과 시군구 목록', note)
            page.get_by_role('button', name='새 주제', exact=True).click()
            dialog = page.locator('dialog:visible')
            choose(page, 'dialog:visible [name=district_id]', '종로구')
            dialog.locator('[name=title]').fill('종로 2026년 10월 행사 일정')
            dialog.locator('[name=is_demo]').uncheck()
            snap(frames, '지역 뉴스 2/7 · 종로구 운영 주제 등록', note)
            dialog.get_by_role('button', name='주제 저장', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(page.locator('#newsWorkspace')).to_contain_text('종로 2026년 10월 행사 일정')
            page.get_by_role('button', name='CSV·JSON 가져오기', exact=True).click()
            dialog = page.locator('dialog:visible')
            dialog.locator('input[type=file]').set_input_files(str(ROOT / 'data/news/jongno_20261020/jongno_events_20261020.csv'))
            snap(frames, '지역 뉴스 3/7 · 준비된 종로 행사 CSV 선택', note)
            dialog.get_by_role('button', name='파일 가져오기', exact=True).click()
            expect(page.locator('dialog:visible')).to_have_count(0)
            expect(page.locator('#newsWorkspace')).to_contain_text('JN20261024_FAMILY_SCHEDULE')
            snap(frames, '지역 뉴스 4/7 · 원자료 3건과 Fact 후보 저장', note, 2800)
            # 문서의 출처 입력 항목도 실제 화면에서 보여줍니다. 수정은 저장하지 않습니다.
            page.locator('[data-news-action=source][data-id]').first.click()
            dialog = page.locator('dialog:visible')
            expect(dialog.locator('[name=source_url]')).to_have_value(re.compile(r'^https://'))
            snap(frames, '지역 뉴스 5/7 · 출처 종류·발행 기관·제목·원문 URL', note, 2800)
            dialog.locator('[name=license_note]').scroll_into_view_if_needed()
            snap(frames, '지역 뉴스 6/7 · 공개 시점 UTC·관련 구절·이용 조건', note, 2800)
            dialog.get_by_role('button', name='닫기', exact=True).click()
            page.locator('[data-news-action=verify]').first.scroll_into_view_if_needed()
            snap(frames, '지역 뉴스 7/7 · Fact별 원문 대조를 기다리는 상태', note, 2800)
            cur.execute('SELECT COUNT(*) FROM news_sources'); assert cur.fetchone()[0] == 3
            cur.execute("SELECT COUNT(*) FROM news_facts WHERE status='candidate'"); assert cur.fetchone()[0] == 8
            cur.execute('SELECT COUNT(*) FROM news_fact_evidence'); assert cur.fetchone()[0] == 8
            for table in ('news_drafts', 'news_publications', 'news_ai_usage'):
                cur.execute(f'SELECT COUNT(*) FROM {table}'); assert cur.fetchone()[0] == 0
            assert not errors, errors
            # 관리자 하단 Google 로고 같은 정적 이미지 요청도 차단하지만 API 호출과 구별합니다.
            assert not [r for r in external_requests if r['type'] != 'image'], external_requests
            save(frames, 'news', '지역 뉴스 — 종로 CSV 가져오기와 출처 입력 항목',
                 '실제 공개 행사 CSV로 **출처 3건·Fact 후보 8건·근거 연결 8건**을 저장했습니다. 출처 편집 화면의 입력 항목도 확인했습니다. **AI 생성·Fact 검증 완료·승인·게시는 시연하지 않았습니다.**',
                 '종로 지역 뉴스 주제를 만들고 CSV를 가져와 출처와 검증 대기 Fact를 확인한 실제 화면')
            recorded = datetime.now(timezone(timedelta(hours=9)))
            manifest_file = ASSETS / 'demo-recordings.json'
            previous = json.loads(manifest_file.read_text(encoding='utf-8')) if manifest_file.exists() else {}
            updated_files = {item['file'] for item in recordings}
            recordings += [item for item in previous.get('recordings', []) if item['file'] not in updated_files and (ROOT / item['file']).is_file()]
            manifest = {'recorded_at': recorded.isoformat(timespec='seconds'),
                        'environment': f'{recorded:%Y-%m-%d} {platform.system()} Chromium {browser.version} · Node.js/실제 FastAPI · MySQL {mysql_version}의 **격리된 임시 테스트 DB**에서 녹화했습니다. 운영 PC의 실행 결과와 구분합니다. OpenAI·노션은 호출하지 않았습니다.',
                        'recordings': recordings}
            (ASSETS / 'demo-recordings.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            metrics.update({'mysql': mysql_version, 'chromium': browser.version, 'browser_errors': errors,
                            'blocked_external_images': len(external_requests), 'external_browser_api_requests': 0,
                            'sources': 3, 'candidate_facts': 8,
                            'evidence_links': 8, 'drafts': 0, 'publications': 0, 'ai_usage': 0, 'travel_steps': 12})
            (RESULTS / 'summary.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            browser.close()
            print('README 실행 화면 검증 완료: 한국/일본 추천, 여행 12단계, 뉴스 후보 8건', flush=True)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        for handle in handles:
            handle.close()
        # 삭제 대상은 도구가 방금 만든 임시 DB 한 개뿐입니다.
        if not re.fullmatch(r'news_test_ui_[0-9a-f]{10}', name):
            raise RuntimeError('임시 DB 이름 검증 실패')
        cur.execute(f'DROP DATABASE IF EXISTS `{name}`')
        cur.close(); conn.close()


if __name__ == '__main__':
    # urllib의 하위 모듈을 명시적으로 불러 Windows/Linux 양쪽에서 사용합니다.
    import urllib.request
    import urllib.parse
    main()
