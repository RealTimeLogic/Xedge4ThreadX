"""Build and audit RT1020 firmware. This command does not fetch dependencies or flash."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
from fetch import DEFAULT_CACHE


def run(command, log, env):
    with log.open('w', encoding='utf-8', newline='\n') as output:
        process = subprocess.Popen([str(a) for a in command], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, env=env)
        for line in process.stdout:
            output.write(line)
            print(line, end='', flush=True)
        if process.wait():
            raise RuntimeError(f'Command failed; see {log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deps', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--build', type=Path, default=ROOT/'build')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/rt1020-evk')
    parser.add_argument('--ide', type=Path, help='MCUXpresso IDE installation directory')
    parser.add_argument('--epoch', type=int, help='Fixed UTC Unix seconds for the build-time clock floor')
    args = parser.parse_args()
    env = os.environ.copy()
    if args.epoch is not None:
        if not 1767225600 <= args.epoch < 0xffffffff:
            parser.error('--epoch must be UTC Unix seconds in the supported 2026 through U32 range')
        env['SOURCE_DATE_EPOCH'] = str(args.epoch)
    if args.ide:
        compilers = list(args.ide.glob('ide/plugins/**/arm-none-eabi-gcc.exe'))
    elif shutil.which('arm-none-eabi-gcc'):
        compilers = [Path(shutil.which('arm-none-eabi-gcc'))]
    else:
        compilers = sorted(Path('C:/nxp').glob('MCUXpressoIDE*/ide/plugins/**/arm-none-eabi-gcc.exe'), reverse=True)[:1]
    if len(compilers) != 1:
        raise RuntimeError('Select one MCUXpresso installation with --ide or put Arm GCC on PATH')
    cmake, ninja = shutil.which('cmake'), shutil.which('ninja')
    if not (cmake and ninja):
        vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        vs = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-property', 'installationPath'], text=True).strip()
        base = Path(vs)/'Common7/IDE/CommonExtensions/Microsoft/CMake'
        cmake, ninja = base/'CMake/bin/cmake.exe', base/'Ninja/ninja.exe'
    if not (Path(cmake).is_file() and Path(ninja).is_file()):
        raise RuntimeError('Install CMake and Ninja, or the Visual Studio CMake tools')
    env['PATH'] = os.pathsep.join([str(compilers[0].parent), str(Path(ninja).parent), env['PATH']])
    args.output.mkdir(parents=True, exist_ok=True)
    run([compilers[0], '--version'], args.output/'compiler.log', env)
    configure = [cmake, '-S', ROOT, '-B', args.build.resolve(), '-G', 'Ninja',
                 f'-DCMAKE_MAKE_PROGRAM={Path(ninja).as_posix()}',
                 f'-DCMAKE_TOOLCHAIN_FILE={(ROOT/"cmake/arm-gcc.cmake").as_posix()}',
                 f'-DDEPS:PATH={args.deps.resolve().as_posix()}', '-DCMAKE_BUILD_TYPE=Release']
    if args.epoch is not None:
        configure.append(f'-DRT1020_BUILD_EPOCH={args.epoch}')
    run(configure, args.output/'configure.log', env)
    run([cmake, '--build', args.build.resolve(), '-j', '8'], args.output/'build.log', env)
    run([sys.executable, ROOT/'tools/audit.py', args.build.resolve(), args.output.resolve()], args.output/'audit.log', env)


if __name__ == '__main__':
    main()
