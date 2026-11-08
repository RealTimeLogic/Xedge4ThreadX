# Dependency ownership and adaptations

This project combines Real Time Logic software, Eclipse ThreadX middleware,
and NXP board support. Each dependency retains its own license and notices.

The [BAS](https://github.com/RealTimeLogic/BAS) and
[BAS-Resources](https://github.com/RealTimeLogic/BAS-Resources) submodules select
the runtime and resource revisions. [dependencies.lock.json](dependencies.lock.json)
records the downloaded SDK and RTOS inputs. The build generates Lua/web
resources and the adapted files listed below without editing the downloaded
source trees. Retain the dependencies' license files when redistributing them.

| Input | Origin and role |
| --- | --- |
| BAS | Real Time Logic public amalgamated BAS, matching headers, ThreadX/FileX ports, allocator and Xedge host in the `BAS/` submodule. Retain `BAS/LICENSE`. |
| BAS-Resources | `BAS-Resources/` submodule for Lua/web sources and public generation scripts, including Windows `zip.exe` and `bin2c.exe`. Its commit and selected resource features must match BAS; generated files are build outputs. |
| ThreadX, NetX Duo, FileX, LevelX | Eclipse ThreadX middleware, at the revisions in `dependencies.lock.json`. |
| SDK 26.09 components | NXP core drivers, RT device/startup files, board examples, PHY/UART/flash components and CMSIS. |
| NetX adapter | `NXP/azure-rtos`, pinned separately from SDK 26.09. |
| Storage example | `nxp-mcuxpresso/legacy-mcux-sdk-examples`, separately pinned FileX/LevelX adapter and linker input. |

[boards/rt1020-evk/adaptations/prepare.py](boards/rt1020-evk/adaptations/prepare.py)
verifies the input hashes before generating these integration changes:

| Generated file | Local adaptation |
| --- | --- |
| `nx_driver_imxrt.c` | Stage outgoing Ethernet frames in aligned, noncached memory, leaving NetX packet data and pointers intact for retransmission. Retain vendor receive, interrupt and completion paths. |
| `lx_mflash_driver.c` | Limit erased-sector verification to the sector buffer actually read, and align the page-program buffer. |
| `rt1020.ld` | Reserve the FileX partition, put ordinary BSS in SDRAM, reserve noncached DMA memory, increase C heap/system stack and enforce the firmware boundary. |

The accompanying `nx_driver_imxrt.h` is copied unchanged to select the matching
driver header. Generated files retain their original notices. These are local
integration adaptations, not changes supplied or accepted by NXP or Eclipse.
The adaptations are specific to this board project.
