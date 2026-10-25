"""记录本轮真实回归结果，并用独立集成库验证完整快照接收。"""
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / '成员2补交_2026-10-12'
EVIDENCE = PACKAGE / 'docs/evidence'
INTEGRATION = PACKAGE / '附件/集成验证工作副本'


def run(label, args, cwd):
    result = subprocess.run([sys.executable, '-X', 'utf8', *args], cwd=cwd,
                            capture_output=True, encoding='utf-8',
                            env=dict(os.environ, PYTHONUTF8='1'))
    (EVIDENCE / f'{label}.log').write_text(f'cwd={cwd}\ncommand={args}\nexit={result.returncode}\n'
                                         + result.stdout + result.stderr, encoding='utf-8')
    print(label, result.returncode)
    if result.returncode:
        print(result.stdout + result.stderr)
        raise SystemExit(result.returncode)


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for name in ('corpus.py', 'parser.py', 'fetcher.py', 'crawler.py'):
        shutil.copy2(ROOT / 'src' / name, INTEGRATION / 'src' / name)
    shutil.copy2(ROOT / 'tests/test_followup_f1_f2.py', INTEGRATION / 'tests/test_followup_f1_f2.py')
    shutil.copy2(ROOT / 'config.yaml', INTEGRATION / 'config.yaml')
    run('返工测试', ['-m', 'unittest', 'discover', '-s', 'tests', '-v'], ROOT)
    run('成员1集成兼容测试', ['-m', 'unittest', 'discover', '-s', 'tests', '-v'], INTEGRATION)
    run('依赖检查', ['-m', 'pip', 'check'], ROOT)
    version = {line.split('==')[0]: importlib.metadata.version(line.split('==')[0])
               for line in (ROOT / 'requirements-lock.txt').read_text().splitlines() if '==' in line}
    (EVIDENCE / '本轮环境.json').write_text(json.dumps(dict(python=sys.version, dependencies=version), indent=2)+'\n', encoding='utf-8')
    database = EVIDENCE / '独立接收验证.db'
    if database.exists():
        raise RuntimeError('Refusing to reuse existing integration test database')
    corpus = str(PACKAGE / 'data/corpus.jsonl')
    run('快照导入', ['-m', 'src.main', '--db', str(database), '--import-corpus', corpus], INTEGRATION)
    run('重复快照导入', ['-m', 'src.main', '--db', str(database), '--import-corpus', corpus], INTEGRATION)
    run('活动文档质检', ['-m', 'src.main', '--db', str(database), '--quality', '--quality-source', 'documents',
                           '--quality-output', str(EVIDENCE / '独立接收质量.json')], INTEGRATION)
    print('All follow-up validations passed; production database untouched.')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
