"""Windows 배치와 PowerShell에서 같은 검증 명령을 실행하고 결과를 파일로 남깁니다."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description='뉴스 코드·DB·브라우저 검증 실행기')
    parser.add_argument('--mode', choices=('offline', 'mysql', 'browser'), default='offline')
    args = parser.parse_args()
    env = dict(os.environ)
    # 무료 실행은 호출자의 MYSQL 테스트 플래그를 무시해 운영 DB를 요구하지 않습니다.
    env['NEWS_TEST_MYSQL'] = '0'
    commands = []
    if args.mode != 'browser':
        node = shutil.which('node')
        if not node:
            print('Node.js 설치를 확인하세요.');return 1
        commands.append([node, '--check', 'server.js'])
        commands.append([node, '--test', *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'tests').glob('*.test.js'))]])
        commands.append([sys.executable, '-m', 'pytest', 'tests/news', '-q'])
        if args.mode == 'mysql':
            env['NEWS_TEST_MYSQL'] = '1'
    else:
        commands.append([sys.executable, str(ROOT / 'tests/news/browser_smoke.py')])
    folder = ROOT / 'test-results';folder.mkdir(exist_ok=True)
    report = {'mode': args.mode, 'started_at': datetime.now(timezone.utc).isoformat(),
              'live_openai_called': False, 'checks': []}
    log_path = folder / ('checks-' + args.mode + '.log')
    with log_path.open('w', encoding='utf-8') as log:
        for command in commands:
            # API 키/DB 비밀번호 같은 환경 값은 로그로 출력하지 않습니다.
            display = ' '.join([Path(command[0]).name, *command[1:]])
            print('\n실행:', display, flush=True)
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            print(process.stdout, flush=True);log.write(display + '\n' + process.stdout + '\n')
            report['checks'].append({'command': display, 'exit_code': process.returncode, 'passed': process.returncode == 0})
            if process.returncode:
                break
    report['passed'] = len(report['checks']) == len(commands) and all(c['passed'] for c in report['checks'])
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    report_path = folder / ('checks-' + args.mode + '.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(('통과' if report['passed'] else '실패') + ': ' + str(report_path))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
