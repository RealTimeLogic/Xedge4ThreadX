"""Verify submodules and fetch locked RTOS/SDK inputs. Never overwrite edits."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import urllib.request
from sources import inspect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT/'.deps'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def install_files(target, entries):
    # Check an existing tree in full before writing any missing files.
    for name, data in entries.items():
        p = target/name
        if p.exists() and (not p.is_file() or p.read_bytes() != data):
            raise RuntimeError(f'Refusing to overwrite changed input: {p}')
    for name, data in entries.items():
        p = target/name
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)


def fetch(item, cache):
    name, spec = item
    archive = cache/f'{name}-{spec["commit"]}.tar.gz'
    if not archive.exists():
        temporary = archive.with_suffix('.partial')
        url = f'https://codeload.github.com/{spec["repo"]}/tar.gz/{spec["commit"]}'
        print('Downloading', name, flush=True)
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as out:
            shutil.copyfileobj(response, out)
        if digest(temporary.read_bytes()) != spec['sha256']:
            raise RuntimeError(f'Archive checksum mismatch: {name}')
        temporary.replace(archive)
    if digest(archive.read_bytes()) != spec['sha256']:
        raise RuntimeError(f'Archive checksum mismatch: {archive}')
    entries = {}
    with tarfile.open(archive) as tar:
        for member in tar:
            parts = PurePosixPath(member.name).parts[1:]
            if not parts or '..' in parts or not member.isfile():
                continue
            relative = '/'.join(parts)
            if 'paths' in spec and not any(relative.startswith(p) for p in spec['paths']):
                continue
            entries[relative] = tar.extractfile(member).read()
    install_files(cache/name, entries)
    manifest = dict(spec, files={n:digest(b) for n,b in sorted(entries.items())})
    (cache/name/'.xedge-source.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    print('Verified', name, spec['commit'], len(entries), 'files', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    print('Submodules:', json.dumps(inspect()), flush=True)
    locked = json.loads((ROOT/'dependencies.lock.json').read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda item: fetch(item, args.cache.resolve()), locked.items()))


if __name__ == '__main__':
    main()
