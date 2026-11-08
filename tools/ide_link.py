"""Run the native linker, preserving diagnostics and its exit status for CDT."""
from pathlib import Path
import re
import subprocess
import sys


# CDT bundled with MCUXpresso 25.06 mistakes these GNU ld informational notes
# for errors. Keep the original stream in linker.log and label only this exact
# note in the console. Warnings, errors and all other output pass unchanged.
NOTE = re.compile(r'^.*[/\\]ld(?:\.exe)?: (.+): note: '
                  r'the message above does not take linker garbage collection into account$')


def main():
    with Path('linker.log').open('w', encoding='utf-8', newline='\n') as log:
        process = subprocess.Popen(['arm-none-eabi-gcc', *sys.argv[1:]],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True)
        for line in process.stdout:
            log.write(line)
            match = NOTE.fullmatch(line.rstrip('\r\n'))
            if match:
                print('Linker note: the message above does not take linker garbage '
                      'collection into account (' + match[1] + ')', flush=True)
            else:
                print(line, end='', flush=True)
        return process.wait()


if __name__ == '__main__':
    sys.exit(main())
