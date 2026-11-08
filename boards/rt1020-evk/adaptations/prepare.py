"""Generate reviewed adaptations; never modify pinned vendor source trees."""
import hashlib
import json
import pathlib
import sys

deps, out = map(pathlib.Path, sys.argv[1:])
for name, expected in json.loads((pathlib.Path(__file__).parent / "inputs.json").read_text()).items():
    if hashlib.sha256((deps / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"Unexpected vendor input: {name}")
out.mkdir(parents=True, exist_ok=True)
sample = deps / "examples/evkmimxrt1020/azure_rtos_examples/filex_levelx_mflash"
text = (sample / "armgcc/MIMXRT1021xxxxx_flexspi_nor.ld").read_text()
text = text.replace("0x007FDC00", "0x003FDC00")
text = text.replace("  m_ncache", "  m_sdram               (RW)  : ORIGIN = 0x80000000, LENGTH = 0x01E00000\n  m_ncache", 1)
text = text.replace("ORIGIN = 0x20200000, LENGTH = 0x00020000", "ORIGIN = 0x81E00000, LENGTH = 0x00200000")
# All ordinary BSS (including the BAS heap) goes in cacheable SDRAM; packet
# buffers and ENET descriptors explicitly use the separate noncacheable area.
text = text.replace("  } > m_ncache\n\n  .heap", "  } > m_sdram\n\n  .heap")
text = text.replace("0x0400;", "0x4000;")
text += '\nASSERT(__DATA_END <= 0x60400000, "Firmware overlaps FileX partition")\n'
(out / "rt1020.ld").write_text(text, newline="\n")
text = (sample / "lx_mflash_driver.c").read_text()
# The SDK example checks 8192 bytes in a 512-byte buffer. Limit this loop to
# the sector that was actually read. Give the program staging buffer alignment.
old = "i < LX_NOR_BLOCK_SIZE / sizeof(uint32_t)"
assert text.count(old) == 1
text = text.replace(old, "i < LX_NOR_SECTOR_SIZE_BYTES / sizeof(uint32_t)")
text = text.replace("int8_t wbuf[MFLASH_PAGE_SIZE];", "uint32_t aligned_wbuf[MFLASH_PAGE_SIZE / sizeof(uint32_t)];\n    uint8_t *wbuf = (uint8_t *)aligned_wbuf;")
(out / "lx_mflash_driver.c").write_text(text, newline="\n")

# The pinned ENET driver moves unaligned packet bytes without restoring NetX's
# pointers. Stage each Ethernet frame in aligned DMA memory instead; retain the
# vendor RX, interrupt, queue and completion paths and leave the SDK untouched.
text = (deps / "nxp-rtos/ports/netxduo/nx_driver_imxrt.c").read_text()
start = text.index("static UINT  _nx_driver_hardware_packet_send(NX_PACKET *packet_ptr)\n{")
end = text.index("\n}\n", start) + 3
text = text[:start] + (pathlib.Path(__file__).parent / "enet_tx.inc").read_text() + text[end:]
(out / "nx_driver_imxrt.c").write_text(text, newline="\n")
# Preserve the driver's quoted-header lookup; the SDK example has an older
# header with the same filename and no checksum capability definition.
(out / "nx_driver_imxrt.h").write_bytes(
    (deps / "nxp-rtos/ports/netxduo/nx_driver_imxrt.h").read_bytes())
