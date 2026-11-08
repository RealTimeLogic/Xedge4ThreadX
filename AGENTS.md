# Xedge for ThreadX Agent Guide

## Start here

Use this guide to obtain dependencies, build RT1020 firmware from the command
line and upload it without operating the MCUXpresso GUI. The human IDE tutorial
is [README.md](README.md). Both routes use the same sources, board
configuration and generated resources. **MIMXRT1020-EVK is the only target.**

Read the [BAS agent guide](BAS/AGENTS.md) for shared runtime rules. Use the
[native BAS/BWS skill](BAS/skills/build-bas-bws-native-apps/SKILL.md) for C/C++
integration and the [Xedge/Lua skill](BAS/skills/build-xedge-mako-lua-apps/SKILL.md)
for Lua applications. Use both when changing the native/Lua boundary. Keep
board setup here and shared API guidance in BAS, as in the Xedge32 port.

Before changing anything, inspect the parent and both submodules with
`git status --short`. Preserve unrelated edits, user licensing and existing
board files. Follow the task's authorization for installation, building and
hardware access; reference commands below are not a request to execute every
step. Do not commit or publish unless explicitly requested.

For a documentation-only task, read existing evidence and update prose without
invoking setup, builds, image audits, probe tools, resets or runtime checks.
When tests are authorized, agree their scope from the task and retain that
boundary. A quick check does not authorize a full socket matrix or new
power-loss/Ethernet recovery runs.

Keep reports, local test harnesses and historical investigations under ignored
`tests/`. The public build must not require files from that directory. Retain
existing generated driver/linker adaptations and their notices. Do not add
new driver fixes, substitute middleware or change BAS/SharkSSL behavior to
make packaging work. Report a missing capability instead of expanding scope.
Do not run a full soak or a heavy concurrent flash-write campaign.

## 1. Install the Windows tools

Use existing installations when they meet these requirements. Avoid changing
system-wide tool versions for a local task.

| Tool | Requirement and installation source |
| --- | --- |
| Git | [Git for Windows](https://git-scm.com/downloads/win), available as `git` on PATH. |
| Python | [Python for Windows](https://www.python.org/downloads/windows/), 3.11 or newer, including pip and venv; available as `python`. |
| Arm compiler | Arm GCC 14.2.1 supplied with [MCUXpresso IDE 25.06](https://www.nxp.com/design/software/development-software/mcuxpresso-software-and-tools-/mcuxpresso-integrated-development-environment-ide:MCUXpresso-IDE). If absent, download/install that IDE with its USB probe drivers. An NXP sign-in or installer interaction may require the user. No GUI project import is needed for this route. |
| CMake and Ninja | CMake 3.20 or newer and Ninja on PATH, or the existing Visual Studio CMake tools. The isolated installation below provides them without installing Visual Studio. |
| Programming and serial tools | pyOCD 0.46.1 and pyserial 3.5, installed in an isolated Python environment below. The RT1020 target is built into pyOCD; no additional CMSIS pack is needed. |

## 2. Obtain and verify sources

For a new checkout:

```powershell
# Clone with both dependencies; skip this block when a checkout already exists.
git clone --recurse-submodules https://github.com/RealTimeLogic/Xedge4ThreadX.git
cd Xedge4ThreadX
```

Run all remaining commands from that root.

From the repository root, create the environment if it does not already exist:

```powershell
# Install command-line tools locally; no PowerShell activation policy change is needed.
python -m venv .venv
.venv/Scripts/python.exe -m pip install "cmake==3.31.6" "ninja>=1.11,<2" "pyocd==0.46.1" "pyserial==3.5"
$env:PATH = "$PWD/.venv/Scripts;$env:PATH"
cmake --version
ninja --version
```

[CMake's Python distribution](https://pypi.org/project/cmake/3.31.6/) supplies
Windows binaries. Record resolved tool versions with each build. Reapply the
PATH line in a new shell. Use `.venv/Scripts/python.exe` in commands below;
no activation script or administrator shell is needed.

Initialize the parent's recorded submodules, then download the locked
SDK/RTOS inputs:

```powershell
# Inspect changes before initializing or fetching; do not overwrite local work.
git status --short
git -C BAS status --short
git -C BAS-Resources status --short
git submodule update --init --recursive
.venv/Scripts/python.exe tools/sources.py
.venv/Scripts/python.exe tools/fetch.py
```

- `BAS/` is the public amalgamated BAS repository; `BAS-Resources/` supplies
  Lua/web sources and its public Windows resource tools. Gitlinks select the
  compatible revisions. Do not use `git submodule update --remote`, hand-edit
  amalgamations or make hidden submodule patches. Make product changes in their
  authoritative repositories and select obtainable commits after publication.
- `dependencies.lock.json` identifies the SDK 26.09 components and separately
  pinned ThreadX, NetX Duo, FileX, LevelX and legacy NXP adapter/example inputs.
  `fetch.py` verifies archive hashes and extracted files. It refuses to replace
  changed inputs. The initial download includes a legacy examples archive of
  about 1.6 GB; retain `.deps` for reuse.
- No private BAS SDK, copied source snapshot, pre-generated resource payload
  or delivery ZIP is required. Builds generate resource C from BAS-Resources,
  including OPC UA and native softTPM, into ignored build output. Resource ZIP
  data is an intermediate runtime format, not a separately supplied dependency.

SDK downloads and the IDE installer are separate. Do not replace the locked
SDK inputs with whatever an IDE wizard currently offers. See
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for ownership and adaptations.

## 3. Compile and audit

Select the installed IDE directory explicitly when several toolchains exist.
This command uses its compiler, CMake and Ninja to build the optimized
**Release** configuration; it does not start the IDE, fetch dependencies or
access the board. The human IDE project instead builds **Debug**:

```powershell
# Use fresh output directories for a new qualification build.
.venv/Scripts/python.exe tools/build.py --ide C:/nxp/MCUXpressoIDE_25.6.136 --build build-cli --output dist/rt1020-cli
```

Stop on any nonzero exit. Read `configure.log`, `build.log` and `audit.log` in
`dist/rt1020-cli`. A successful run supplies:

| Output | Use |
| --- | --- |
| `xedge.bin`, `xedge.elf`, `xedge.map` | Firmware, debug symbols and memory map. |
| `image-review.json` | Binary SHA-256, features, memory/boot checks, compiler and input provenance. Its status means build-reviewed, not hardware-qualified. |
| `source-sha256.json`, `compile_commands.json` | Actual inputs and compiler invocations. |
| `resources.json` | Resource settings and input/output hashes. |
| `compiler.log`, `configure.log`, `build.log`, `audit.log` | Build and audit evidence. |

The audit requires clean dependency submodules and checks the boot headers,
firmware partition, RAM-resident flash routines, native time/RNG/mDNS symbols,
OPC UA/resources and required socket settings. Do not disable assertions or
weaken these checks to obtain a passing result. Keep compiler/linker warnings
in the record. No hardware pass follows merely from compiling or auditing.

Use a fresh build directory after changing the compiler, dependency location
or CMake source root. Existing caches may refer to an earlier layout. To use
an external cache, pass the same path to `fetch.py --cache PATH` and
`build.py --deps PATH`.

## 4. Identify, connect and upload

Have the user connect the board as described in
[README: board connections](README.md#4-connect-the-board-and-serial-terminal).
Confirm the correct physical target before programming. Both board power and
the debug data connection must be present; a USB serial port alone does not
prove that the RT1020 core is powered. Keep Ethernet connected to DHCP/DNS.

End any LinkServer/J-Link/other pyOCD session using the probe. Identify the
probe and serial port without opening a firmware-programming session:

```powershell
# Record the exact probe ID and actual COM port; do not use a hard-coded lab ID.
.venv/Scripts/python.exe -m pyocd list
.venv/Scripts/python.exe -m serial.tools.list_ports
```

Open a second terminal from the repository root for startup logs. Replace
`COM_PORT` with the port just discovered:

```powershell
# Keep only one serial monitor attached; Ctrl+] exits miniterm.
.venv/Scripts/python.exe -m serial.tools.miniterm COM_PORT 115200 --raw
```

When programming is within the task's scope, replace `PROBE_ID` with the
complete discovered ID and choose an output directory that does not exist:

```powershell
# Sector erase preserves FileX; the adjacent image-review.json must match the binary.
.venv/Scripts/python.exe tools/flash.py --probe PROBE_ID --image dist/rt1020-cli/xedge.bin --output dist/flash-cli-01 --erase sector
```

`flash.py` selects `mimxrt1020`, checks the reviewed image hash and its 4 MiB
boundary, uses a system reset, programs the firmware sectors, reads back every
byte, compares it and resumes execution. Success requires exit zero,
`RT1020_FLASH_VERIFIED` and `flash.json` with `complete: true` and matching
image/readback hashes. Inspect that JSON after any failure; it records whether
programming began. Do not infer success from probe enumeration.

`--verify-only` resets, reads back and boots the installed image without
programming. It still interrupts execution. `--erase chip` destroys FileX
applications/settings too; use it only if the user requested whole-chip erase.
Normal updates use sector erase. Never run simultaneous hardware operations.

`--verify-only` compares the complete BIN representation used by this CLI
programmer. For an IDE ELF download, compare the ELF load segments instead:
LinkServer leaves unused gaps erased (`0xff`), while `objcopy -O binary`
fills those gaps with zero. A raw BIN hash mismatch alone therefore does not
prove that an IDE-programmed image differs. Retain both image identities and
the segment/padding comparison. A failed readback can leave the CPU halted;
restore execution before handing the board back.

## 5. Check startup and hand back a usable board

Wait for `FILEX_READY`, `XEDGE_IPV4` and `XEDGE_THREADX_READY` in the serial log.
Use the printed address, not an address from an earlier run. Open
`http://ADDRESS/rtl/`. Check a small save/run/reboot using the
[README Lua example](README.md#7-save-and-run-a-lua-application) when runtime
checks are authorized. Internet time produces `SNTP UTC` followed by
`SNTP_EVENT UTC`; client TLS needs the correct clock. Record actual results,
not just the expected markers.

Retain exact source/image identities and distinguish build, programming,
readback, normal-use checks and broader protocol acceptance. Run only the
finite tests requested for the task. Remove temporary application fixtures,
leave the board running, and tell the user its current address. Preserve
existing applications, credentials and certificates.

Before ending a hardware task:

1. Remove only the temporary files, routes and services created for that task.
   Do not reset Xedge configuration or delete the user's applications.
2. End owned debug/probe sessions and release the serial port. Check that the
   CPU is running after a failed readback or halted debug session. Report any
   unresolved halt instead of presenting an old address as a working UI.
3. Retain the build and programming records under ignored output directories.
   State the build route/configuration, source and submodule revisions, BIN
   and ELF hashes, input/resource manifests, tool versions and exact tests run.
   Record working-tree differences when the parent is uncommitted; a parent
   commit alone cannot identify those files.
4. Report the observed URL, clock status, file-persistence result and cleanup,
   limited to what was checked in this task. Label older results by image and
   date. Distinguish development-certificate HTTPS from trusted client TLS or
   a newly enrolled SharkCA hostname.
5. List deferred checks and the heavy concurrent flash-write limitation. Do
   not turn an interrupted full matrix with passing cases into a full pass,
   or report physical recovery from a software-reset check.

For a documentation handoff without fresh hardware work, identify the last
recorded evidence as historical. Do not reconnect to the board merely to
refresh its address. Keep private result paths and credentials out of the
public README; it should remain a reusable procedure.

## Source and configuration contracts

Compile exactly one `BAS/src/BAS.c`, its matching separate ThreadX thread/socket
ports, FileX port, allocator, Xedge host, board startup and generated resources.
Do not add separate Lua/SharkSSL objects already in the amalgamation.

Keep these enabled in the RT1020 profile: IPv4/IPv6, socket write events,
blocking/asynchronous Lua sockets and cosockets, UDP, native NetX mDNS,
SharkSSL/embedded CA/native softTPM, OPC UA, time synchronization and FileX.
No PSA backend or additional-board support is implied.

The shared headers derive IPv6 from NetX. Socket write events require
`NX_ENABLE_EXTENDED_NOTIFY_SUPPORT` and
`NX_ENABLE_TCP_QUEUE_DEPTH_UPDATE_NOTIFY`. Native mDNS also needs UDP and,
for IPv6, `NX_ENABLE_IPV6_MULTICAST`. Build middleware and BAS with the same
configuration headers. Do not add the BSD `BamDNS-Sock.c` adapter here.
Preserve packet chaining, partial-write, timeout and close/cancellation
behavior; the UI alone cannot establish complete socket compatibility.

| Memory | Allocation |
| --- | --- |
| Firmware | `0x60000000..0x603fffff`, lower 4 MiB of QSPI flash. |
| FileX/LevelX | `0x60400000..0x607fffff`, upper 4 MiB. |
| Cacheable SDRAM | 30 MiB at `0x80000000`, including the 24 MiB BAS heap. |
| Noncached SDRAM | 2 MiB at `0x81e00000` for network/DMA storage. |
| DTCM | 64 KiB at `0x20000000`, including RAM-resident flash routines. |

ROM initializes SDRAM from the image's device configuration data (DCD).
Preserve that initialization, MPU/cache setup, linker layout and `*.c.obj`
object names: the linker identifies flash-writing code by object name.
If FileX cannot mount, this evaluation startup erases/formats its data
partition. Heavy concurrent flash writes remain outside the accepted normal
interactive workload.

## Command options and IDE maintenance

| Option | Type, default and meaning |
| --- | --- |
| `fetch.py --cache` | Optional directory path; default `.deps`. |
| `build.py --deps` | Optional verified dependency directory; default `.deps`. |
| `build.py --build` | Optional generated-source/object directory; default `build`. |
| `build.py --output` | Optional audited-image/log directory; default `dist/rt1020-evk`. |
| `build.py --ide` | Optional MCUXpresso installation directory. Otherwise uses Arm GCC on PATH or searches `C:/nxp`. |
| `build.py --epoch` | Optional integer UTC Unix seconds, 1767225600 through 4294967294. Defaults to first configure time in the CMake cache. An explicit value also sets `SOURCE_DATE_EPOCH`. SNTP replaces this startup clock floor. |
| `flash.py --probe` | Required exact probe ID string. |
| `flash.py --image` | Required BIN path; matching `image-review.json` must be alongside it. |
| `flash.py --output` | Required new directory for the readback/programming record. |
| `flash.py --erase` | Optional string `sector` (default) or `chip`. |
| `flash.py --verify-only` | Optional flag, default false; reset/readback/boot without programming. |
| `flash.py --frequency` | Optional integer SWD frequency in Hz; default 1000000. |

`tools/setup_ide.py` prepares the native IDE route. `tools/generate_ide.py
--build BUILD` regenerates `.project`, `.cproject`, Make additions and
`profile.json` from a configured CMake build. It is not needed for a routine
IDE build. Preserve archive boundaries/order and per-source settings when
regenerating metadata. The native IDE project defaults to Debug (`-Og -g3`,
assertions enabled); CMake remains the optimized route. The profile supports native build audit
and reproducible project maintenance; it is a public input, not a test report.

`tools/audit.py BUILD OUTPUT` audits a CMake build. With `--ide-log LOG`, it
audits a native IDE build using a complete successful clean-build log and its
actual compiler commands. Put the matching Arm compiler and Ninja on PATH
before invoking the audit directly. Public `tools/resources.py --output DIR`
and `tools/ide_prepare.py --output DIR [--epoch SECONDS]` generate inputs;
normal build entry points invoke them automatically.

The native Debug and optimized CMake images are not expected to be
byte-identical. Audit and qualify each configuration separately. Reproducible
rebuilds of the same configuration need the same explicit startup epoch and
`SOURCE_DATE_EPOCH`; the IDE preparation helper accepts `--epoch`.

IDE debugging also requires NXP's installed EVK-MIMXRT1020 device-support
package. The project associates `SDK_2.x_EVK-MIMXRT1020`, device-support version
2.11.0, core and board metadata. The `.project` must also contain
`com.nxp.mcuxpresso.core.datamodels.sdkNature`; NXP uses this marker to validate
the installed package and populate its device-support cache when opening the
project. Close and reopen an already imported project after changing this
metadata. Without the marker, SDK path resolution can throw an internal
exception and leave LinkServer without its `--server` arguments, followed by
a misleading GDB localhost connection error. The SDK association does not
select firmware sources: those
remain SDK 26.09 from `.deps`. Keep the explicit ELF linker output type and
target-tool selection. The portable `Xedge_RT1020 Debug.launch` contains the
complete Startup scripts, UART semihosting Off, SYSRESETREQ and the NXP connect
script; it must not contain a local probe serial number or absolute path.

The `BOARD_FLASH` region in `.cproject` selects NXP's installed
`MIMXRT1020-EVK_IS25LP064.cfx`. Keep that choice in the generator too. Use the
EVK-specific loader in this memory region; a global `--flash-driver` launch
option does not replace the per-region selection. For a flash-initialization
failure, check this setting before considering loader or firmware changes.

The portable launch sets the working directory to the IDE project and maps
GDB's reproducible source paths: `build/boards` and `build/resources` to
`Debug/boards` and `Debug/resources`, `deps` to `../../../.deps`, and `build`
to `../../..`. Keep the more specific mappings first. This resolves source
files without embedding a checkout path or changing firmware bytes. After
changing launch metadata, check stop-at-main, source stepping, and Resume.
Record those debug checks separately from socket or runtime qualification.

## Repository handoff

The public handoff consists of the parent sources, the two recorded Gitlinks,
`dependencies.lock.json`, the native IDE project/portable launch, build tools,
licenses, third-party notices, and the README and agent guide. Keep the human
IDE tutorial in README.md and CLI procedures here. Link directly to the
relevant guide instead of adding pointer-only Markdown files. Do not include
source snapshots, delivery ZIPs, compiled images, `.deps`, IDE workspaces or test
evidence in the parent. A separately requested binary needs its image and
source provenance alongside it.

Review README commands against the shipped helpers and launch metadata before
changing them. Compare the same build configuration when making reproducibility
claims. A copied working tree is not a fresh clone of a published parent;
record that distinction if publication or a clean-clone walkthrough is deferred.
When documenting an IDE update, keep installed device-support version,
firmware SDK version, compiler and LinkServer version separate.
