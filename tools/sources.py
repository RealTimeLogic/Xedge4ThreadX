"""Check the parent's recorded submodule revisions without updating working trees."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def inspect(require_clean=False):
    result = {}
    for name in ('BAS', 'BAS-Resources'):
        path = ROOT / name
        if not (path / '.git').exists():
            raise RuntimeError('Missing submodule ' + name +
                               '; run git submodule update --init --recursive at the repository root')
        entry = git(ROOT, 'ls-files', '--stage', '--', name).split()
        if len(entry) != 4 or entry[0] != '160000':
            raise RuntimeError('Missing parent Git submodule pointer: ' + name)
        revision = git(path, 'rev-parse', 'HEAD')
        if revision != entry[1]:
            raise RuntimeError(name + ' differs from the parent submodule pointer; preserve edits before updating')
        status = git(path, 'status', '--porcelain', '--untracked-files=normal')
        if require_clean and status:
            raise RuntimeError('Qualification requires a clean submodule: ' + name)
        result[name] = {'commit': revision, 'dirty': bool(status)}
    return result


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2))
