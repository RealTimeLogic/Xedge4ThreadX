"""Validate RT1020 image placement, enabled features and compiler inputs; stage artifacts."""
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import zipfile
from sources import inspect


def command_args(command):
    if sys.platform != "win32":
        return shlex.split(command)
    # compile_commands.json uses Windows quoting and backslashes on Windows.
    import ctypes
    split = ctypes.windll.shell32.CommandLineToArgvW
    split.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    split.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    argv = split(command, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError()
    try:
        return [argv[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))


def config_macros(command, directory):
    args = command_args(command)
    idx = args.index("-o")
    del args[idx:idx+2]
    args.remove("-c")
    for flag in ('-MMD', '-MP'):
        if flag in args:
            args.remove(flag)
    for flag in ('-MF', '-MT'):
        if flag in args:
            idx = args.index(flag)
            del args[idx:idx+2]
    args += ["-dM", "-E"]
    text = subprocess.check_output(args, cwd=directory, text=True)
    return dict(re.findall(r"^#define (\w+) ?(.*)$", text, re.M))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('build', type=pathlib.Path)
parser.add_argument('output', type=pathlib.Path)
parser.add_argument('--ide-log', type=pathlib.Path, help='Successful complete native build log, optionally followed by successful incremental logs')
options = parser.parse_args()
build, output = options.build.resolve(), options.output.resolve()
output.mkdir(parents=True, exist_ok=True)
binary = (build / "xedge.bin").read_bytes()
assert 0x2400 < len(binary) < 4 * 1024 * 1024, "Firmware exceeds its flash partition"
assert struct.unpack_from("<I", binary)[0] == 0x42464346, "Missing FlexSPI boot configuration"
ivt = struct.unpack_from("<8I", binary, 0x1000)
assert ivt[0] == 0x412000D1 and ivt[5] == 0x60001000, "Invalid MCUXpresso v4.1 boot IVT"
assert 0x60001000 <= ivt[3] < 0x60002000, "Missing ROM SDRAM DCD"
stack, reset = struct.unpack_from("<2I", binary, 0x2000)
assert 0x20000000 < stack <= 0x20010000 and reset & 1, "Invalid reset vectors"
nm = subprocess.check_output(["arm-none-eabi-nm", "-n", str(build / "xedge.elf")], text=True)
symbols = {}
for line in nm.splitlines():
    fields = line.split()
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)
for name in ("mflash_drv_init", "mflash_drv_sector_erase", "mflash_drv_page_program",
             "FLEXSPI_UpdateLUT", "FLEXSPI_TransferBlocking", "DCACHE_InvalidateByRange", "customLUT"):
    assert 0x20000000 <= symbols[name] < 0x20010000, f"Flash operation is not in RAM: {name}"
assert symbols["__DATA_END"] <= 0x60400000
assert 0x81E00000 <= symbols["txFrames"] < 0x82000000 - 64 * 1536, "ENET staging is not in noncached SDRAM"
here = pathlib.Path(__file__).resolve().parents[1]
if options.ide_log:
    build_log = options.ide_log.read_text(errors='replace')
    assert re.search(r'Build Finished\. 0 errors, \d+ warnings\.', build_log), 'IDE build did not pass'
    assert 'Build Failed.' not in build_log and 'Finished building target: xedge.elf' in build_log
    commands = []
    for line in build_log.splitlines():
        if line.startswith('arm-none-eabi-gcc ') and ' -c ' in line:
            argv = command_args(line)
            source = pathlib.Path(argv[argv.index('-c')+1]).resolve()
            argv[0] = shutil.which('arm-none-eabi-gcc')
            commands.append(dict(directory=str(build), file=source.as_posix(),
                                 command=subprocess.list2cmdline(argv)))
    # A retained clean build plus later successful incremental logs records
    # the actual latest invocation for every source, without inventing commands.
    commands = list({c['file']: c for c in commands}.values())
    profile_path = here / 'ide/mcuxpresso/rt1020-evk/profile.json'
    profile = json.loads(profile_path.read_text())
    expected = {pathlib.Path(s['path'].replace('${ProjDirPath}', build.parent.as_posix())).resolve()
                for s in profile['sources']}
    assert len(commands) == len(expected) == profile['source_count'], 'Need a complete clean IDE build log'
    assert {pathlib.Path(c['file']) for c in commands} == expected, 'IDE source inventory differs'
    dependency_root = here / '.deps'
    (build / 'compile_commands.json').write_text(json.dumps(commands, indent=2) + '\n', encoding='utf-8', newline='\n')
else:
    commands = json.loads((build / "compile_commands.json").read_text())
    cache = (build / "CMakeCache.txt").read_text()
    dependency_root = pathlib.Path(re.search(r"^DEPS:PATH=(.+)$", cache, re.M)[1])
generated = build / "boards/rt1020-evk/generated"
locked = json.loads((here / "dependencies.lock.json").read_text())
provenance = {}
for name, spec in locked.items():
    marker = dependency_root / name / ".xedge-source.json"
    actual = json.loads(marker.read_text())
    assert all(actual.get(k) == v for k, v in spec.items()), f"Dependency lock mismatch: {name}"
    provenance[name] = actual
assert not any("rt1020-2.16" in c["file"] for c in commands), "Old SDK compiled into new image"
driver_versions = {}
for name in ("enet", "flexspi"):
    header = dependency_root / "sdk/drivers" / name / ("fsl_" + name + ".h")
    version = re.search(r"#define FSL_" + name.upper() + r"_DRIVER_VERSION \(MAKE_VERSION\((\d+), (\d+), (\d+)\)\)", header.read_text())
    assert version, f"Missing SDK driver version: {name}"
    driver_versions[name] = ".".join(version.groups())
assert driver_versions == {"enet": "2.11.4", "flexspi": "2.9.3"}, driver_versions
phy = next(c for c in commands if c["file"].endswith("/fsl_phyksz8081.c"))
assert "-DFSL_FEATURE_PHYKSZ8081_USE_RMII50M_MODE" in command_args(phy["command"]), "Missing EVK PHY reference-clock setting"
main = next(c for c in commands if c["file"].endswith("/XedgeStartup.c"))
if options.ide_log:
    build_epoch = int(re.search(r'^#define RT1020_BUILD_EPOCH (\d+)$', (build / 'build_epoch.h').read_text(), re.M)[1])
else:
    build_epoch = int(next(a.split("=", 1)[1] for a in command_args(main["command"])
                          if a.startswith("-DRT1020_BUILD_EPOCH=")))
assert 1767225600 <= build_epoch < 0xFFFFFFFF, "Invalid startup clock fallback"
core = next(c for c in commands if c["file"].endswith("/BAS/src/BAS.c"))
args = command_args(core["command"])
macros = config_macros(core["command"], build)
assert "NDEBUG" not in macros, "Assertions disabled"
features = ["BA_ENABLE_IPV6", "BA_HAVE_SOCKET_WRITE_EVENTS", "BA_ENABLE_UDP",
    "BA_ENABLE_MDNS", "BA_ENABLE_MDNS_LUA", "BA_ENABLE_SHARKSSL", "BA_ENABLE_EMBEDDED_CA", "BA_ENABLE_TPM", "BA_ENABLE_LUA_OPCUA",
    "BA_ENABLE_LUA_DEBUGGER", "BA_ENABLE_UBJSON", "BA_ENABLE_WEBDAV", "BA_ENABLE_REVERSE_CONNECTION",
    "BA_ENABLE_REVERSE_PROXY"]
for name in features:
    assert macros.get(name) == "1", f"Feature not enabled: {name}"
# Host defaults belong to XedgeConfig.h, which BAS.c does not include.
host = next(c for c in commands if c["file"].endswith("/BAS/examples/xedge/src/xedge.c"))
host_macros = config_macros(host["command"], build)
assert host_macros.get("BA_ENABLE_SHARKTRUST") == "1", "SharkTrust not enabled in Xedge"
assert host_macros.get("XEDGE_USE_DEFAULT_DISK_IO_INIT") == "0", "Xedge must use board FileX initialization"
assert "NX_DISABLE_IPV6" not in macros
for name in ["NX_ENABLE_EXTENDED_NOTIFY_SUPPORT", "NX_ENABLE_TCP_QUEUE_DEPTH_UPDATE_NOTIFY", "NX_ENABLE_TCP_KEEPALIVE",
             "NX_DHCP_CLIENT_USER_CREATE_PACKET_POOL", "NX_DNS_CLIENT_USER_CREATE_PACKET_POOL",
             "NX_ENABLE_INTERFACE_CAPABILITY", "NX_ENABLE_IPV6_MULTICAST"]:
    assert name in macros, name
resource_dir = build / 'resources'
with zipfile.ZipFile(resource_dir / "Xedge.zip") as archive:
    assert archive.testzip() is None
    entries = archive.namelist()
    for name in [".config", ".lua/tpm.lua", ".lua/opcua/init.lua", ".lua/mqttc.lua", ".lua/smqbroker.lua"]:
        assert name in entries, name
inputs = {pathlib.Path(c["file"]).resolve() for c in commands}
assert (here / "boards/rt1020-evk/adaptations/enet_tx.inc").read_text() in (generated / "nx_driver_imxrt.c").read_text(), "Stale ENET adaptation"
inputs.update(here / name for name in
              ("CMakeLists.txt", "cmake/arm-gcc.cmake", "boards/rt1020-evk/CMakeLists.txt", "boards/rt1020-evk/adaptations/prepare.py", "boards/rt1020-evk/adaptations/inputs.json", "boards/rt1020-evk/adaptations/enet_tx.inc", "tools/audit.py", "dependencies.lock.json", ".gitmodules", "tools/sources.py", "tools/resources.py"))
inputs.update(dependency_root / name / ".xedge-source.json" for name in locked)
if options.ide_log:
    for dep in build.glob('*/*.d'):
        content = dep.read_text().replace('\\\n', '')
        first = content.split('\n', 1)[0].split(': ', 1)[1]
        for value in shlex.split(first):
            path = pathlib.Path(value)
            if not path.is_absolute(): path = build / path
            assert path.is_file(), 'Missing IDE input: ' + str(path)
            inputs.add(path.resolve())
    inputs.update(here / 'tools' / name for name in ('ide_prepare.py', 'ide_link.py'))
    inputs.update((here / 'tools/generate_ide.py', profile_path))
    inputs.update(build.parent / name for name in ('.project', '.cproject', 'makefile.defs', 'makefile.targets'))
else:
    deps = subprocess.check_output(["ninja", "-C", str(build), "-t", "deps"], text=True)
    for line in deps.splitlines():
        if line.startswith("    "):
            path = pathlib.Path(line.strip())
            if not path.is_absolute(): path = build / path
            if path.is_file(): inputs.add(path.resolve())
# A customer build can only consume this checkout, its build tree, the locked
# dependency cache and compiler headers. No private full-source/test inputs.
compiler_dir = pathlib.Path(args[0]).resolve().parent.parent
allowed = [here, build, dependency_root.resolve(), compiler_dir]
for path in inputs:
    assert any(path.is_relative_to(base) for base in allowed), f"Undeclared input: {path}"
assert sum(c["file"].endswith("/BAS/src/BAS.c") for c in commands) == 1
assert not any(c["file"].endswith("/BWS.c") for c in commands)
submodules = inspect(require_clean=True)
resources = json.loads((resource_dir / "resources.json").read_text())
assert resources['submodules'] == submodules, 'Resources were built from different submodules'
for name, expected in resources["files"].items():
    assert hashlib.sha256((resource_dir / name).read_bytes()).hexdigest() == expected, name
for name, expected in resources['inputs'].items():
    path = here / 'BAS-Resources' / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    inputs.add(path)
inputs.add(resource_dir / 'resources.json')
for name, spec in provenance.items():
    for relative, expected in spec["files"].items():
        assert hashlib.sha256((dependency_root / name / relative).read_bytes()).hexdigest() == expected, relative
assert "time" not in symbols and "sharkssl_entropy" not in symbols
assert all(name in symbols for name in ("BamDNS_luaopen", "BamDNS_getNetInfo", "BamDNS_socketSetup", "BamDNS_socketRecv", "BamDNS_socketSend")), "Missing native mDNS transport"
assert "baGetUnixTime" in symbols and "sharkssl_entropyEx" in symbols
hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs)}
for name in ["xedge.bin", "xedge.elf", "xedge.map", "compile_commands.json"]:
    shutil.copy2(build / name, output / name)
shutil.copy2(resource_dir / 'resources.json', output / 'resources.json')
(output / "source-sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
report = dict(status="build-reviewed-hardware-pending", bytes=len(binary),
    sdk_release="26.09.00", driver_versions=driver_versions,
    dependencies={name: {k:v for k,v in spec.items() if k != "files"} for name,spec in provenance.items()},
    sha256=hashlib.sha256(binary).hexdigest(), compiler=subprocess.check_output(["arm-none-eabi-gcc", "--version"], text=True).splitlines()[0],
    firmware=["0x60000000", "0x603fffff"], filesystem=["0x60400000", "0x607fffff"],
    bas_heap_bytes=24*1024*1024, resources=len(entries), source_inputs=len(hashes), build_epoch=build_epoch,
    assertions=True, features={k:macros[k] for k in features},
    tls={k:v for k,v in macros.items() if "TLS_1_" in k},
    ram_symbols={k:hex(v) for k,v in symbols.items() if k in ["customLUT", "mflash_drv_init", "mflash_drv_sector_erase", "mflash_drv_page_program", "FLEXSPI_TransferBlocking"]})
report["features"]["BA_ENABLE_SHARKTRUST"] = host_macros["BA_ENABLE_SHARKTRUST"]
report["submodules"] = submodules
report["resource_sha256"] = resources['files']
report["distribution_only"] = True
report['build_route'] = 'mcuxpresso-native' if options.ide_log else 'cmake-ninja'
if options.ide_log:
    shutil.copy2(options.ide_log, output / 'build.log')
    shutil.copy2(build / 'linker.log', output / 'linker.log')
report["time_test_server"] = next((a.split("=", 1)[1].strip('"') for a in command_args(main["command"])
    if a.startswith("-DRT1020_TIME_TEST_SERVER=")), None)
assert "synchronizeTime" in symbols and "timeEvent" in symbols, "Missing M12 time implementation"
assert not any("sntp_client" in name for name in symbols), "Full SNTP add-on is still linked"
(output / "image-review.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
