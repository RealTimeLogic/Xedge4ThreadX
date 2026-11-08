"""Erase, program, read back, and boot one explicitly selected RT1020 probe.

Run only after the board is connected/configured. Sector erase preserves FileX.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target
from pyocd.flash.file_programmer import FileProgrammer

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--probe", required=True, help="Exact ID from pyocd list")
parser.add_argument("--image", type=pathlib.Path, required=True)
parser.add_argument("--output", type=pathlib.Path, required=True)
parser.add_argument("--verify-only", action="store_true", help="Reset and verify the installed image without erasing or programming")
parser.add_argument("--erase", choices=("chip", "sector"), default="sector", help="Use sector for subsequent firmware updates without erasing the test filesystem")
parser.add_argument("--frequency", type=int, default=1000000, help="SWD clock in Hz")
args = parser.parse_args()
review = json.loads(args.image.with_name("image-review.json").read_text())
data = args.image.read_bytes()
assert hashlib.sha256(data).hexdigest() == review["sha256"], "Image differs from reviewed build"
assert len(data) < 4 * 1024 * 1024
args.output.mkdir(parents=True, exist_ok=False)
report = dict(complete=False, stage="connect", programming_started=False,
    probe=args.probe, target="mimxrt1020", erase_mode="none" if args.verify_only else args.erase,
    image=str(args.image.resolve()), sha256=review["sha256"], swd_frequency=args.frequency)
try:
    session = ConnectHelper.session_with_chosen_probe(blocking=False, unique_id=args.probe,
        target_override="mimxrt1020", frequency=args.frequency,
        connect_mode="attach" if args.verify_only else "under-reset", resume_on_disconnect=False)
    if session is None: raise RuntimeError("Selected probe is not connected")
    with session:
        assert session.probe.unique_id == args.probe, "Probe ID must match exactly"
        target = session.target
        # The i.MX RT default is core-only VECTRESET. A running RTOS leaves
        # SysTick/peripheral interrupts active across that reset, so use a
        # system reset and mask interrupts before executing the RAM algorithm.
        report["reset_type"] = "SYSRESETREQ"
        if not args.verify_only:
            target.reset_and_halt(Target.ResetType.SYSRESETREQ)
            target.write_core_register("primask", 1)
            target.write32(0xE000E010, 0)  # SysTick CTRL
            target.flush()
            report.update(stage="program", programming_started=True)
            FileProgrammer(session, chip_erase=args.erase, smart_flash=args.erase == "sector", trust_crc=False,
                           keep_unwritten=False).program(str(args.image), base_address=0x60000000)
        report["stage"] = "readback"
        # Let ROM initialize FlexSPI from the installed boot header and SDRAM
        # from DCD. Core-only reset can leave mapped reads shifted by a byte.
        entry = struct.unpack_from("<I", data, 0x2004)[0] & ~1
        target.reset_and_halt(Target.ResetType.SYSRESETREQ)
        assert target.set_breakpoint(entry, Target.BreakpointType.HW)
        try:
            target.resume()
            deadline = time.monotonic() + 10
            while target.get_state() != Target.State.HALTED and time.monotonic() < deadline:
                time.sleep(0.01)
            assert target.get_state() == Target.State.HALTED, "ROM did not reach application entry"
            assert target.read_core_register("pc") == entry, "Unexpected boot halt"
        finally:
            target.remove_breakpoint(entry)
        readback = bytearray()
        for offset in range(0, len(data), 4096):
            readback.extend(target.read_memory_block8(0x60000000 + offset, min(4096, len(data)-offset)))
        report["readback_sha256"] = hashlib.sha256(readback).hexdigest()
        if readback != data: raise RuntimeError("Full firmware readback mismatch")
        target.resume()
        report["complete"] = True
        report["stage"] = "booted"
        report["programming_time_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print("RT1020_FLASH_VERIFIED", review["sha256"])
except Exception as error:
    report["error"] = str(error)
    raise
finally:
    (args.output / "flash.json").write_text(json.dumps(report, indent=2) + "\n", newline="\n")
