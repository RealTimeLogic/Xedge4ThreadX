"""MCUXpresso pre-build: prepare generated inputs without compiling firmware."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from resources import generate, write_changed
from sources import ROOT, inspect


def prepare(output, epoch=None):
    inspect()
    deps = ROOT / '.deps'
    for name, spec in json.loads((ROOT / 'dependencies.lock.json').read_text()).items():
        marker = deps / name / '.xedge-source.json'
        if not marker.is_file():
            raise RuntimeError('Missing SDK/RTOS inputs; run python tools/fetch.py at the repository root')
        actual = json.loads(marker.read_text())
        if any(actual.get(k) != v for k, v in spec.items()):
            raise RuntimeError('SDK/RTOS lock mismatch: ' + name)
    board = ROOT / 'boards/rt1020-evk'
    output.mkdir(parents=True, exist_ok=True)
    # On first import MCUXpresso may clean before generating its managed
    # Makefile. Supply only that harmless bootstrap target; CDT replaces it.
    makefile = output / 'makefile'
    if not makefile.exists():
        write_changed(makefile, b'# Bootstrap for the first CDT clean.\nclean:\n\t@echo Initial generated inputs ready\n')
    for component, prefix in (('threadx', 'tx'), ('netxduo', 'nx'), ('filex', 'fx'), ('levelx', 'lx')):
        target = output / 'boards/rt1020-evk' / component / 'custom_inc'
        target.mkdir(parents=True, exist_ok=True)
        write_changed(target / (prefix + '_user.h'), (board / 'config' / (prefix + '_user.h')).read_bytes())
    subprocess.run([sys.executable, str(board / 'adaptations/prepare.py'),
                    str(deps), str(output / 'boards/rt1020-evk/generated')], check=True)
    epoch_header = output / 'build_epoch.h'
    if epoch is not None or not epoch_header.exists():
        value = int(epoch if epoch is not None else os.environ.get('SOURCE_DATE_EPOCH', time.time()))
        if not 1767225600 <= value < 0xffffffff:
            raise RuntimeError('Build epoch is outside the supported 2026 through U32 range')
        write_changed(epoch_header, ('/* Startup fallback; SNTP supplies the actual time. */\n'
                                     '#define RT1020_BUILD_EPOCH ' + str(value) + '\n').encode())
    generate(output / 'resources')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'ide/mcuxpresso/rt1020-evk/Debug')
    parser.add_argument('--epoch', type=int)
    args = parser.parse_args()
    prepare(args.output.resolve(), args.epoch)
