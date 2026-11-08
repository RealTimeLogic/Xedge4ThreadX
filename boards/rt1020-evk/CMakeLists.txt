cmake_minimum_required(VERSION 3.20)
project(xedge_rt1020 LANGUAGES C ASM)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(BOARD_SOURCE_DIR "${PUBLIC_ROOT}/boards/rt1020-evk")
set(BAS_ROOT "${PUBLIC_ROOT}/BAS")
if(NOT DEFINED DEPS)
  message(FATAL_ERROR "Set DEPS to the verified dependency cache; run tools/fetch.py first")
endif()
set(ECLIPSE "${DEPS}")
set(SDK "${DEPS}/sdk")
set(COMPONENTS "${DEPS}/components")
set(DEVICE "${DEPS}/devices/RT1020/MIMXRT1021")
set(BOOT "${DEPS}/devices/RT1050/MIMXRT1052/xip")
set(BOARD "${DEPS}/board-examples/_boards/evkmimxrt1020")
set(PINS "${BOARD}/driver_examples/enet/txrx_transfer")
# NXP no longer ships NetX/FileX adapters in the current SDK. Keep the
# explicitly pinned legacy adapters separate from the 26.09 drivers.
set(EXAMPLE "${DEPS}/examples/evkmimxrt1020/azure_rtos_examples")
set(THREADX_ARCH cortex_m7)
set(THREADX_TOOLCHAIN gnu)
set(TX_USER_FILE "${BOARD_SOURCE_DIR}/config/tx_user.h")
set(NX_USER_FILE "${BOARD_SOURCE_DIR}/config/nx_user.h")
set(FX_USER_FILE "${BOARD_SOURCE_DIR}/config/fx_user.h")
set(LX_USER_FILE "${BOARD_SOURCE_DIR}/config/lx_user.h")
set(NXD_ENABLE_FILE_SERVERS OFF CACHE BOOL "" FORCE)
set(NXD_ENABLE_AZURE_IOT OFF CACHE BOOL "" FORCE)
set(NXD_ENABLE_BSD OFF CACHE BOOL "" FORCE)
add_compile_options(-Os -g3 -ffunction-sections -fdata-sections -fno-common -UNDEBUG
  "-ffile-prefix-map=${PUBLIC_ROOT}=."
  "-ffile-prefix-map=${DEPS}=deps"
  "-ffile-prefix-map=${CMAKE_BINARY_DIR}=build")
add_compile_definitions(CPU_MIMXRT1021DAG5A XIP_EXTERNAL_FLASH=1
  XIP_BOOT_HEADER_ENABLE=1 XIP_BOOT_HEADER_DCD_ENABLE=1 SKIP_SYSCLK_INIT
  __STARTUP_INITIALIZE_NONCACHEDATA __STARTUP_CLEAR_BSS
  SDK_DEBUGCONSOLE=1 SDK_DEBUGCONSOLE_UART=1
  SERIAL_PORT_TYPE_UART=1 LX_USE_MFLASH)
# The EVK supplies a 50 MHz RMII reference to the KSZ8081 PHY.
set_source_files_properties("${COMPONENTS}/phy/device/phyksz8081/fsl_phyksz8081.c"
  PROPERTIES COMPILE_DEFINITIONS FSL_FEATURE_PHYKSZ8081_USE_RMII50M_MODE)
# Cache the initial configure time for reproducible rebuilds. It is only a
# startup clock floor; SNTP replaces it when a network time update arrives.
string(TIMESTAMP INITIAL_BUILD_EPOCH "%s" UTC)
set(RT1020_BUILD_EPOCH "${INITIAL_BUILD_EPOCH}" CACHE STRING "UTC build-time clock fallback")
set_source_files_properties("${BOARD_SOURCE_DIR}/XedgeStartup.c" PROPERTIES COMPILE_DEFINITIONS "RT1020_BUILD_EPOCH=${RT1020_BUILD_EPOCH}")
add_subdirectory("${ECLIPSE}/threadx" threadx)
add_subdirectory("${ECLIPSE}/netxduo" netxduo)
add_subdirectory("${DEPS}/filex" filex)
add_subdirectory("${DEPS}/levelx" levelx)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${PUBLIC_ROOT}/tools/sources.py"
  COMMAND_ERROR_IS_FATAL ANY)
set(RESOURCE_DIR "${CMAKE_BINARY_DIR}/resources")
file(GLOB_RECURSE RESOURCE_INPUTS CONFIGURE_DEPENDS
  "${PUBLIC_ROOT}/BAS-Resources/src/core/*"
  "${PUBLIC_ROOT}/BAS-Resources/src/xedge/*"
  "${PUBLIC_ROOT}/BAS-Resources/src/opcua/*")
add_custom_command(OUTPUT "${RESOURCE_DIR}/XedgeZip.c"
  BYPRODUCTS "${RESOURCE_DIR}/Xedge.zip" "${RESOURCE_DIR}/resources.json"
  COMMAND "${Python3_EXECUTABLE}" "${PUBLIC_ROOT}/tools/resources.py" --output "${RESOURCE_DIR}"
  DEPENDS ${RESOURCE_INPUTS} "${PUBLIC_ROOT}/tools/resources.py"
    "${PUBLIC_ROOT}/tools/sources.py" "${BOARD_SOURCE_DIR}/config/BaConfigOpts.h"
    "${PUBLIC_ROOT}/BAS-Resources/build/Xedge.cmd"
    "${PUBLIC_ROOT}/BAS-Resources/tools/windows/zip.exe"
    "${PUBLIC_ROOT}/BAS-Resources/tools/windows/bin2c.exe"
  VERBATIM)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${BOARD_SOURCE_DIR}/adaptations/prepare.py"
  "${DEPS}" "${CMAKE_CURRENT_BINARY_DIR}/generated" COMMAND_ERROR_IS_FATAL ANY)
set(DRIVERS common igpio lpuart enet trng flexspi cache/armv7-m7)
set(DRIVER_SOURCES)
set(DRIVER_INCLUDES)
foreach(D IN LISTS DRIVERS)
  get_filename_component(N "${D}" NAME)
  if(D STREQUAL "igpio")
    set(N gpio)
  elseif(D STREQUAL "cache/armv7-m7")
    set(N cache)
  endif()
  list(APPEND DRIVER_SOURCES "${SDK}/drivers/${D}/fsl_${N}.c")
  list(APPEND DRIVER_INCLUDES "${SDK}/drivers/${D}")
endforeach()
add_executable(xedge.elf "${BOARD_SOURCE_DIR}/XedgeStartup.c"
  "${RESOURCE_DIR}/XedgeZip.c"
  "${CMAKE_CURRENT_BINARY_DIR}/generated/lx_mflash_driver.c"
  "${EXAMPLE}/filex_levelx_mflash/fx_levelx_driver.c"
  "${PINS}/pin_mux.c"
  "${BOARD}/board.c" "${BOARD}/common/clock/clock_config.c" "${BOARD}/dcd.c"
  "${BOARD}/xip/evkmimxrt1020_flexspi_nor_config.c"
  "${DEVICE}/system_MIMXRT1021.c"
  "${DEVICE}/gcc/startup_MIMXRT1021.S"
  "${DEVICE}/drivers/fsl_clock.c"
  "${BOOT}/fsl_flexspi_nor_boot.c"
  ${DRIVER_SOURCES}
  "${COMPONENTS}/phy/device/phyksz8081/fsl_phyksz8081.c"
  "${COMPONENTS}/uart/fsl_adapter_lpuart.c"
  "${COMPONENTS}/debug_console_lite/fsl_debug_console.c"
  "${COMPONENTS}/str/fsl_str.c"
  "${COMPONENTS}/assert/fsl_assert.c"
  "${SDK}/drivers/common/fsl_common_arm.c"
  "${COMPONENTS}/flash/mflash/mimxrt1021/mflash_drv.c"
  "${CMAKE_CURRENT_BINARY_DIR}/generated/nx_driver_imxrt.c"
  "${DEPS}/nxp-rtos/ports/netxduo/nx_driver_imxrt_irq.c"
  "${BAS_ROOT}/src/BAS.c"
  "${BAS_ROOT}/src/dlmalloc.c"
  "${BAS_ROOT}/examples/xedge/src/xedge.c"
  "${BAS_ROOT}/src/arch/ThreadX/SoDisp.c"
  "${BAS_ROOT}/src/arch/ThreadX/ThreadLib.c"
  "${BAS_ROOT}/src/DiskIo/FileX/BaFile.c")
target_include_directories(xedge.elf BEFORE PRIVATE "${BOARD_SOURCE_DIR}/config"
  "${BAS_ROOT}/inc/arch/ThreadX" "${BAS_ROOT}/inc"
  "${BAS_ROOT}/examples/xedge/src"
  "${DEVICE}" "${DEVICE}/drivers"
  "${BOOT}" "${DEPS}/cmsis/Core/Include"
  "${BOARD}" "${BOARD}/xip" "${BOARD}/common/clock" "${PINS}"
  "${DEPS}/devices/RT1020/periph"
  "${EXAMPLE}/filex_levelx_mflash" ${DRIVER_INCLUDES}
   "${COMPONENTS}/phy"
  "${COMPONENTS}/phy/device/phyksz8081" "${COMPONENTS}/uart"
  "${COMPONENTS}/serial_manager" "${COMPONENTS}/lists"
  "${COMPONENTS}/assert" "${COMPONENTS}/str" "${COMPONENTS}/debug_console_lite"
  "${COMPONENTS}/flash/mflash" "${COMPONENTS}/flash/mflash/mimxrt1021"
  "${DEPS}/nxp-rtos/ports/netxduo")
target_link_libraries(xedge.elf PRIVATE azrtos::netxduo azrtos::levelx m)
target_link_options(xedge.elf PRIVATE --specs=nosys.specs
  "-T${CMAKE_CURRENT_BINARY_DIR}/generated/rt1020.ld"
  "-Wl,-Map=${CMAKE_BINARY_DIR}/xedge.map,--gc-sections,--print-memory-usage")
set_property(TARGET xedge.elf APPEND PROPERTY LINK_DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/generated/rt1020.ld")
set_target_properties(xedge.elf PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
add_custom_command(TARGET xedge.elf POST_BUILD
  COMMAND arm-none-eabi-objcopy -O binary "$<TARGET_FILE:xedge.elf>" "${CMAKE_BINARY_DIR}/xedge.bin"
  COMMAND arm-none-eabi-size "$<TARGET_FILE:xedge.elf>")
