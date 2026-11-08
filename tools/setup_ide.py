"""Prepare public dependencies and generated inputs before importing into MCUXpresso."""
import subprocess
import sys

from ide_prepare import prepare
from sources import ROOT


if __name__ == '__main__':
    # Initial generated source links must exist when CDT first scans the project.
    # Every later IDE build runs the same generator automatically.
    subprocess.run([sys.executable, str(ROOT / 'tools/fetch.py')], check=True)
    prepare(ROOT / 'ide/mcuxpresso/rt1020-evk/Debug')
