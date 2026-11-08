"""Generate this RT1020 profile's resources using the public Windows generator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from sources import ROOT, inspect


def write_changed(path, data):
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def generate(output):
    revisions = inspect()
    source = ROOT / 'BAS-Resources'
    output = output.resolve()
    if output == ROOT or output.is_relative_to(source) or output.is_relative_to(ROOT / 'BAS'):
        raise RuntimeError('Resource output must be a separate build directory')
    output.mkdir(parents=True, exist_ok=True)
    inputs = {}
    # A new isolated directory prevents optional neighboring repositories or
    # old generated files from changing this fixed native-softTPM profile.
    with tempfile.TemporaryDirectory(prefix='stage-', dir=output) as temporary:
        stage = Path(temporary) / 'BAS-Resources'
        for name in ('core', 'xedge', 'opcua'):
            origin = source / 'src' / name
            shutil.copytree(origin, stage / 'src' / name,
                            ignore=shutil.ignore_patterns('*~', '*.bak', '.git'))
            for p in sorted(origin.rglob('*')):
                if p.is_file() and not p.name.endswith(('~', '.bak')):
                    inputs[p.relative_to(source).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        work = stage / 'build'
        work.mkdir()
        generator = source / 'build/Xedge.cmd'
        shutil.copyfile(generator, work / 'Xedge.cmd')
        windows = source / 'tools/windows'
        for p in (generator, windows / 'zip.exe', windows / 'bin2c.exe'):
            if not p.is_file():
                raise RuntimeError('Missing public resource tool: ' + str(p))
            inputs[p.relative_to(source).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        env = os.environ.copy()
        env.update(BA_ENABLE_LUA_OPCUA='1', SHARKSSL_PSA_CONSUMER='0',
                   MinifyXedgeZip='no', NO_BIN2C='1')
        env['PATH'] = str(windows) + os.pathsep + env['PATH']
        subprocess.run(['cmd.exe', '/d', '/c', 'Xedge.cmd'], cwd=work, env=env, check=True)
        archive_path = output / 'Xedge.zip'
        normalized = work / 'normalized.zip'
        with zipfile.ZipFile(work / 'Xedge.zip') as original, zipfile.ZipFile(normalized, 'w') as archive:
            if original.testzip() is not None:
                raise RuntimeError('Public generator produced a corrupt archive')
            for name in sorted(original.namelist()):
                if name.endswith('/'):
                    continue
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, original.read(name), compresslevel=9)
        with zipfile.ZipFile(normalized) as archive:
            names = archive.namelist()
            for name in ('.config', '.lua/tpm.lua', '.lua/seed.lua', '.lua/acme/runtime.lua',
                         '.lua/opcua/init.lua', '.lua/opcua/model/packed_provider.lua'):
                if name not in names:
                    raise RuntimeError('Required resource absent: ' + name)
            if '.certificate/cacert.shark' in names:
                raise RuntimeError('This profile uses the CA store compiled into BAS')
            if archive.read('.lua/tpm.lua') != (source / 'src/xedge/.lua/tpm.lua').read_bytes():
                raise RuntimeError('Resource TPM backend does not match native SharkSSL')
        cfile = work / 'XedgeZip.c'
        subprocess.run([str(windows / 'bin2c.exe'), '-z', 'getLspZipReader',
                        normalized.name, cfile.name], cwd=work, check=True)
        write_changed(archive_path, normalized.read_bytes())
        write_changed(output / 'XedgeZip.c', cfile.read_bytes().replace(b'\r\n', b'\n'))
    manifest = {'submodules': revisions, 'opcua': True, 'psa': False, 'minified': False,
                'files': {p: hashlib.sha256((output / p).read_bytes()).hexdigest()
                          for p in ('Xedge.zip', 'XedgeZip.c')}, 'inputs': inputs,
                'entries': names}
    write_changed(output / 'resources.json', (json.dumps(manifest, indent=2) + '\n').encode())
    print('Generated', len(names), 'resources in', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    generate(parser.parse_args().output)
