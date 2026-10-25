"""补交打包：相对路径、逐文件 SHA、保留旧证据，排除验证工作副本/DB。"""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / '成员2补交_2026-10-12'


def main():
    delivered = ['src/corpus.py', 'src/parser.py', 'src/crawler.py', 'src/fetcher.py', 'config.yaml',
                 'tests/test_followup_f1_f2.py', 'docs/返工完成说明.md',
                 'docs/交接单_成员1与成员2实施_至成员3.md', 'scripts/verify_followup_f3.py']
    for rel in delivered:
        target = PACKAGE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    shutil.copytree(ROOT / '传回成员2_2026-10-12', PACKAGE / '附件/传回记录', dirs_exist_ok=True)
    shutil.copytree(ROOT / '.agents/skills/team-handoff', PACKAGE / '.agents/skills/team-handoff', dirs_exist_ok=True)
    diff = []
    for rel in delivered[:5]:
        before = (PACKAGE / '附件/返工前' / rel).read_text(encoding='utf-8').splitlines(keepends=True)
        after = (ROOT / rel).read_text(encoding='utf-8').splitlines(keepends=True)
        diff.extend(difflib.unified_diff(before, after, fromfile='before/'+rel, tofile='after/'+rel))
    (PACKAGE / 'docs/evidence/F1_F2_F3修改.diff').write_text(''.join(diff), encoding='utf-8')
    paths = [p for p in PACKAGE.rglob('*') if p.is_file()
             and '集成验证工作副本' not in p.parts and '__pycache__' not in p.parts
             and p.suffix not in ('.db', '.pyc', '.zip')
             and p.name != '交付文件清单.json']
    paths.sort(key=lambda p: str(p.relative_to(PACKAGE)))
    manifest = [dict(file=p.relative_to(PACKAGE).as_posix(), bytes=p.stat().st_size,
                     sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    manifest_path = PACKAGE / 'docs/evidence/交付文件清单.json'
    manifest_path.write_text(json.dumps(dict(version=PACKAGE.name, files=manifest,
        note='Actual delivery file hashes; excludes this manifest and private validation working copy/database.'),
        ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    paths.append(manifest_path)
    archive = ROOT / (PACKAGE.name + '.zip')
    if archive.exists():
        raise RuntimeError('Refusing to overwrite existing archive')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            zf.write(path, path.relative_to(PACKAGE).as_posix())
    with zipfile.ZipFile(archive) as zf:
        assert len(zf.namelist()) == len(paths)
        for entry in manifest:
            assert hashlib.sha256(zf.read(entry['file'])).hexdigest() == entry['sha256']
        assert not any(n.endswith(('.db', '.pyc')) or '.venv' in n for n in zf.namelist())
    print(json.dumps(dict(archive=str(archive), files=len(paths), bytes=archive.stat().st_size,
                          sha256=hashlib.sha256(archive.read_bytes()).hexdigest()), ensure_ascii=False))


if __name__ == '__main__':
    main()
