"""Maintainer tool: derive native MCUXpresso metadata from configured CMake commands."""
import argparse
import ctypes
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as E

from sources import ROOT

PROJECT = ROOT / 'ide/mcuxpresso/rt1020-evk'
NAME = 'Xedge_RT1020'
PREFIX = '${ProjDirPath}/../../..'
OUT = '${ProjDirPath}/Debug'


def split(command):
    fn = ctypes.windll.shell32.CommandLineToArgvW
    fn.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    fn.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    argv = fn(command, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError()
    try:
        return [argv[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))


def xml(path, root):
    E.indent(root, space='  ')
    version = b'<?fileVersion 4.0.0?>\n' if path.name == '.cproject' else b''
    path.write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n' + version + E.tostring(root, encoding='utf-8') + b'\n')


def generate(build):
    commands = json.loads((build / 'compile_commands.json').read_text())
    cache = (build / 'CMakeCache.txt').read_text()
    deps = Path(re.search(r'^DEPS:PATH=(.+)$', cache, re.M)[1]).as_posix()
    roots = [(build.as_posix(), OUT), (deps, PREFIX + '/.deps'), (ROOT.as_posix(), PREFIX)]

    def portable(value):
        value = value.replace('\\', '/')
        for old, new in roots:
            value = value.replace(old, new)
        if re.search(r'[A-Za-z]:/', value):
            raise RuntimeError('Unmapped workstation path: ' + value)
        return value

    groups = {}
    source_records = []
    for item in commands:
        args = split(item['command'])[1:]
        target = re.search(r'CMakeFiles[\\/](.*?)\.dir', item['command'])[1]
        if target not in ('xedge.elf', 'threadx', 'netxduo', 'filex', 'levelx'):
            continue
        i = args.index('-o')
        del args[i:i+2]
        i = args.index('-c')
        del args[i:i+2]
        args = [portable(a) for a in args]
        # The human IDE project is a source-debug build, independent of the
        # optimized CMake profile used to obtain its source/link inventory.
        args = [a for a in args if not a.startswith(('-O', '-g')) and a != '-DNDEBUG']
        args += ['-Og', '-g3']
        for i, arg in enumerate(args):
            if arg.startswith('-DRT1020_BUILD_EPOCH='):
                args[i:i+1] = ['-include', OUT + '/build_epoch.h']
                break
        language = 'gas' if item['file'].endswith(('.S', '.s')) else 'gcc'
        group = {'threadx': 'ThreadX', 'netxduo': 'NetX_Duo', 'filex': 'FileX',
                 'levelx': 'LevelX', 'xedge.elf': 'Application'}[target]
        if language == 'gas':
            group += '_Assembly'
        elif item['file'].endswith('/XedgeStartup.c'):
            group = 'Application_Startup'
        elif item['file'].endswith('/fsl_phyksz8081.c'):
            group = 'Ethernet_PHY'
        spec = {'language': language, 'args': args}
        if group in groups and groups[group] != spec:
            raise RuntimeError('New per-file compiler settings need a separate IDE group: ' + item['file'])
        groups[group] = spec
        source_records.append({'group': group, 'path': portable(item['file']), 'target': target})

    PROJECT.mkdir(parents=True, exist_ok=True)
    project = E.Element('projectDescription')
    E.SubElement(project, 'name').text = NAME
    E.SubElement(project, 'comment').text = 'Xedge for RT1020 with ThreadX, NetX Duo and FileX.'
    E.SubElement(project, 'projects')
    builders = E.SubElement(project, 'buildSpec')
    for name in ('org.eclipse.cdt.managedbuilder.core.genmakebuilder', 'org.eclipse.cdt.managedbuilder.core.ScannerConfigBuilder'):
        b = E.SubElement(builders, 'buildCommand')
        E.SubElement(b, 'name').text = name
        E.SubElement(b, 'triggers').text = 'clean,full,incremental,'
        E.SubElement(b, 'arguments')
    natures = E.SubElement(project, 'natures')
    # NXP validates the installed SDK and resolves debug support only for SDK projects.
    for name in ('org.eclipse.cdt.core.cnature', 'org.eclipse.cdt.managedbuilder.core.managedBuildNature',
                 'org.eclipse.cdt.managedbuilder.core.ScannerConfigNature',
                 'com.nxp.mcuxpresso.core.datamodels.sdkNature'):
        E.SubElement(natures, 'nature').text = name
    links = E.SubElement(project, 'linkedResources')

    def link(name, kind, uri):
        el = E.SubElement(links, 'link')
        E.SubElement(el, 'name').text = name
        E.SubElement(el, 'type').text = str(kind)
        E.SubElement(el, 'locationURI').text = uri

    for group in sorted(groups):
        link(group, 2, 'virtual:/virtual')
    linked = set()
    for source in sorted(source_records, key=lambda s: (s['group'], s['path'])):
        name = source['group'] + '/' + source['path'].rsplit('/', 1)[1]
        if name in linked:
            raise RuntimeError('Duplicate source name: ' + name)
        linked.add(name)
        uri = source['path'].replace(PREFIX, 'PARENT-3-PROJECT_LOC').replace(OUT, 'PROJECT_LOC/Debug')
        link(name, 1, uri)
    xml(PROJECT / '.project', project)

    cp = E.Element('cproject', storage_type_id='org.eclipse.cdt.core.XmlProjectDescriptionStorage')
    settings = E.SubElement(cp, 'storageModule', moduleId='org.eclipse.cdt.core.settings')
    cid = 'com.crt.advproject.config.exe.debug.xedge'
    cc = E.SubElement(settings, 'cconfiguration', id=cid)
    s = E.SubElement(cc, 'storageModule', buildSystemId='org.eclipse.cdt.managedbuilder.core.configurationDataProvider', id=cid, moduleId='org.eclipse.cdt.core.settings', name='Debug')
    E.SubElement(s, 'externalSettings')
    extensions = E.SubElement(s, 'extensions')
    for parser in ('ELF', 'GNU_ELF'):
        E.SubElement(extensions, 'extension', id='org.eclipse.cdt.core.' + parser, point='org.eclipse.cdt.core.BinaryParser')
    s = E.SubElement(cc, 'storageModule', moduleId='cdtBuildSystem', version='4.0.0')
    cfg = E.SubElement(s, 'configuration', id=cid, name='Debug', parent='com.crt.advproject.config.exe.debug',
                       artifactName='xedge', artifactExtension='elf', cleanCommand='rm -rf',
                       buildProperties='org.eclipse.cdt.build.core.buildArtefactType=org.eclipse.cdt.build.core.buildArtefactType.exe',
                       buildArtefactType='org.eclipse.cdt.build.core.buildArtefactType.exe',
                       prebuildStep='echo Generated inputs ready',
                       postbuildStep='echo Firmware outputs ready')
    for group in [''] + sorted(groups):
        f = E.SubElement(cfg, 'folderInfo', id=cid + '.' + (group or 'root'), name=group or '/', resourcePath=group)
        tc = E.SubElement(f, 'toolChain', id='xedge.tc.' + (group or 'root'), name='NXP MCU Tools', superClass='com.crt.advproject.toolchain.exe.debug')
        if not group:
            tc.set('targetTool', 'xedge.link')
            E.SubElement(tc, 'targetPlatform', id='xedge.platform', superClass='com.crt.advproject.platform.exe.debug', binaryParser='org.eclipse.cdt.core.ELF;org.eclipse.cdt.core.GNU_ELF')
            E.SubElement(tc, 'builder', id='xedge.builder', superClass='com.crt.advproject.builder.exe.debug',
                         name='Gnu Make Builder', buildPath='${workspace_loc:/' + NAME + '}/Debug', managedBuildOn='true',
                         parallelBuildOn='true', parallelizationNumber='8', keepEnvironmentInBuildfile='false',
                         arguments='-r -j8 --output-sync=target')
            tool = E.SubElement(tc, 'tool', id='xedge.link', name='MCU Linker', superClass='com.crt.advproject.link.exe.debug', command='python',
                commandLinePattern='${COMMAND} "' + PREFIX + '/tools/ide_link.py" -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard --specs=nosys.specs -T "./boards/rt1020-evk/generated/rt1020.ld" -Wl,-Map=xedge.map,--gc-sections,--print-memory-usage -o "${OUTPUT}" @objects.list')
            E.SubElement(tool, 'option', id='xedge.link.manage', superClass='com.crt.advproject.link.manage', value='false', valueType='boolean')
            E.SubElement(tool, 'outputType', id='xedge.link.output',
                         superClass='cdt.managedbuild.tool.gnu.c.linker.output', outputs='elf')
            inp = E.SubElement(tool, 'inputType', id='xedge.link.input', superClass='cdt.managedbuild.tool.gnu.c.linker.input')
            E.SubElement(inp, 'additionalInput', kind='additionalinputdependency', paths='$(USER_OBJS)')
        else:
            spec = groups[group]
            # Literal configured flags avoid SDK wizard defaults changing the ABI,
            # assertions or per-library configuration. Includes remain visible to indexing.
            def build_arg(arg):
                if arg.startswith('-ffile-prefix-map='):
                    # GCC compares these strings with absolute __FILE__ paths.
                    # Make resolves the relative root before invoking GCC, even
                    # when the checkout path contains spaces.
                    arg = arg.replace(PREFIX + '/.deps', '$(realpath ../../../../.deps)')
                    arg = arg.replace(PREFIX, '$(realpath ../../../..)')
                    arg = arg.replace(OUT, '$(CURDIR)')
                else:
                    # CDT 11's escaping of an absolute active-build path can
                    # introduce literal dollars when the checkout has spaces.
                    # Native Make always runs in Debug; use that relative base.
                    arg = arg.replace(OUT, '.')
                return '"' + arg + '"' if '${ProjDirPath}' in arg or '$(' in arg else subprocess.list2cmdline([arg])
            flags = ' '.join(build_arg(a) for a in spec['args'])
            tool = E.SubElement(tc, 'tool', id='xedge.' + group, name='MCU ' + ('Assembler' if spec['language'] == 'gas' else 'C Compiler'),
                superClass='com.crt.advproject.' + spec['language'] + '.exe.debug', command='arm-none-eabi-gcc',
                commandLinePattern='${COMMAND} ' + flags + ' -MMD -MP -MF "$(@:%.' + ('S' if spec['language'] == 'gas' else 'c') + '.obj=%.d)" -MT "$@" -o ${OUTPUT} -c ${INPUTS}')
            input_base = 'assembler' if spec['language'] == 'gas' else 'compiler'
            E.SubElement(tool, 'inputType', id='xedge.input.' + group, superClass='com.crt.advproject.' + input_base + '.input')
            # The accepted linker script selects flash routines by *.c.obj.
            # Keep CMake's object suffixes instead of changing the linker script.
            E.SubElement(tool, 'outputType', id='xedge.output.' + group,
                superClass='cdt.managedbuild.tool.gnu.' + ('assembler' if spec['language'] == 'gas' else 'c.compiler') + '.output',
                outputs='S.obj' if spec['language'] == 'gas' else 'c.obj', buildVariable='OBJS')
            if spec['language'] == 'gcc':
                opt = E.SubElement(tool, 'option', id='xedge.includes.' + group, superClass='gnu.c.compiler.option.include.paths', valueType='includePath')
                for arg in spec['args']:
                    if arg.startswith('-I'):
                        E.SubElement(opt, 'listOptionValue', builtIn='false', value=arg[2:])
    sources = E.SubElement(cfg, 'sourceEntries')
    for group in sorted(groups):
        E.SubElement(sources, 'entry', flags='VALUE_WORKSPACE_PATH|RESOLVED', kind='sourcePath', name=group)
    bs = E.SubElement(cp, 'storageModule', moduleId='cdtBuildSystem', version='4.0.0')
    E.SubElement(bs, 'project', id=NAME + '.project', name=NAME, projectType='com.crt.advproject.projecttype.exe')
    E.SubElement(cp, 'storageModule', moduleId='org.eclipse.cdt.core.LanguageSettingsProviders')
    # Associate the IDE's installed RT1020 device support. This is debugger
    # metadata only; the compiler still uses the locked sources in .deps.
    sdk = E.SubElement(cp, 'storageModule', moduleId='com.nxp.mcuxpresso.core.datamodels')
    for key, value in (('sdkName', 'SDK_2.x_EVK-MIMXRT1020'), ('sdkVersion', '2.11.0'), ('boardId', 'evkmimxrt1020'),
                       ('core', 'cm7'), ('coreId', 'core0_MIMXRT1021xxxxx'), ('package', 'MIMXRT1021DAG5A')):
        E.SubElement(sdk, key).text = value
    target = E.Element('TargetConfig')
    E.SubElement(target, 'Properties', property_3='NXP', property_4='MIMXRT1021xxxxx', property_count='5', version='100300')
    info = E.SubElement(E.SubElement(target, 'infoList', vendor='NXP'), 'info', chip='MIMXRT1021xxxxx', name='MIMXRT1021xxxxx')
    chip = E.SubElement(info, 'chip')
    for tag, text in (('name', 'MIMXRT1021xxxxx'), ('family', 'MIMXRT1020'), ('vendor', 'NXP')):
        E.SubElement(chip, tag).text = text
    E.SubElement(chip, 'memory', can_program='true', id='Flash', is_ro='true', size='0', type='Flash')
    E.SubElement(chip, 'memory', id='RAM', size='256', type='RAM')
    # Select the supplied EVK loader in the flash region, not a global override.
    E.SubElement(chip, 'memoryInstance', derived_from='Flash', driver='MIMXRT1020-EVK_IS25LP064.cfx', edited='true',
                 id='BOARD_FLASH', location='0x60000000', size='0x400000')
    for name, address, size in (('SRAM_DTC', '0x20000000', '0x10000'), ('SRAM_ITC', '0x0', '0x10000'),
                                ('SRAM_OC', '0x20200000', '0x20000'), ('BOARD_SDRAM', '0x80000000', '0x1e00000'),
                                ('NCACHE_REGION', '0x81e00000', '0x200000')):
        E.SubElement(chip, 'memoryInstance', derived_from='RAM', edited='true', id=name, location=address, size=size)
    processor = E.SubElement(info, 'processor')
    E.SubElement(processor, 'name', gcc_name='cortex-m7').text = 'Cortex-M7'
    E.SubElement(processor, 'family').text = 'Cortex-M'
    E.SubElement(E.SubElement(cp, 'storageModule', moduleId='com.crt.config'), 'projectStorage').text = E.tostring(target, encoding='unicode')
    xml(PROJECT / '.cproject', cp)
    # A probe-independent launch prevents incomplete auto-generated scripts.
    launch = E.Element('launchConfiguration', type='com.crt.dsfdebug.crtmcu.launchType')
    strings = {
        'com.crt.ctrlcenter.OFSemuDetails': 'LinkServer',
        'com.crt.ctrlcenter.currentWireType': 'SWD',
        'com.nxp.mcuxpresso.ide.probe.type': 'LinkServer',
        'com.nxp.mcuxpresso.ide.probe.name': 'CMSIS-DAP',
        'debug.level': '2', 'gdbserver.host': 'localhost', 'gdbserver.port': '10989',
        'internal.wiretype': 'SWD', 'internal.semihost': 'Off',
        'internal.resethandling': 'SYSRESETREQ', 'internal.reset.script': '',
        'internal.connect.script': 'RT1020_connect.scp', 'misc.options': '--no-packed',
        'ondisconnect': 'cont', 'run': 'cont',
        'org.eclipse.cdt.launch.PROJECT_ATTR': NAME,
        'org.eclipse.cdt.launch.WORKING_DIRECTORY': '${workspace_loc:/' + NAME + '}',
        'org.eclipse.cdt.launch.PROGRAM_NAME': 'Debug/xedge.elf',
        'org.eclipse.cdt.launch.PROJECT_BUILD_CONFIG_ID_ATTR': cid,
        'org.eclipse.cdt.launch.DEBUGGER_START_MODE': 'remote',
        'org.eclipse.cdt.dsf.gdb.DEBUG_NAME': 'arm-none-eabi-gdb',
        'org.eclipse.cdt.debug.gdbjtag.core.stopAt': 'main',
        'org.eclipse.cdt.debug.gdbjtag.core.initCommands':
            # Resolve reproducible DWARF paths from the project working directory.
            'set substitute-path build/boards Debug/boards\n'
            'set substitute-path build/resources Debug/resources\n'
            'set substitute-path deps ../../../.deps\n'
            'set substitute-path build ../../..\n'
            'set non-stop on\nset pagination off\nset mi-async\nset remotetimeout 60\n'
            '##target_extended_remote##\nset mem inaccessible-by-default ${mem.access}\n'
            'mon ondisconnect ${ondisconnect}\nset arm force-mode thumb\n${load}\n',
        'org.eclipse.cdt.debug.gdbjtag.core.runCommands': '${run}\n',
    }
    booleans = {'com.crt.ctrlcenter.crtInit': True, 'com.crt.ctrlcenter.saveState': True,
                'com.crt.ctrlcenter.mainBreakIsHardware': True, 'gdbserver.start': True,
                'attach': False, 'mem.access': False, 'vector.catch': True,
                'org.eclipse.cdt.dsf.gdb.NON_STOP': True,
                'org.eclipse.cdt.debug.gdbjtag.core.loadImage': True,
                'org.eclipse.cdt.debug.gdbjtag.core.loadSymbols': True,
                'org.eclipse.cdt.debug.gdbjtag.core.setStopAt': True,
                'org.eclipse.cdt.debug.gdbjtag.core.setResume': False}
    for key, value in strings.items():
        E.SubElement(launch, 'stringAttribute', key=key, value=value)
    for key, value in booleans.items():
        E.SubElement(launch, 'booleanAttribute', key=key, value=str(value).lower())
    E.SubElement(launch, 'intAttribute', key='com.crt.ctrlcenter.version', value='6')
    xml(PROJECT / (NAME + ' Debug.launch'), launch)
    (PROJECT / 'makefile.defs').write_text('# A response file avoids the Windows command-line length limit.\n'
        'USER_OBJS := objects.list\n', encoding='utf-8', newline='\n')
    # Preserve the CMake archive boundaries and member/link order. Passing all
    # middleware objects directly to ld can retain different weak definitions.
    lists = {}
    for source in source_records:
        obj = source['group'] + '/' + Path(source['path']).name + '.obj'
        lists.setdefault(source['target'], []).append(obj)
    archive_recipe = '\t$(RM) libthreadx.a libnetxduo.a libfilex.a liblevelx.a\n'
    for name in ('threadx', 'netxduo', 'filex', 'levelx'):
        archive_recipe += '\t$(file >' + name + '.objects,' + ' '.join(lists[name]) + ')\n'
        archive_recipe += '\tarm-none-eabi-ar rcs lib' + name + '.a @' + name + '.objects\n'
    libraries = re.search(r'^  LINK_LIBRARIES = (.+)$', (build / 'build.ninja').read_text(), re.M)[1].split()
    libraries = [Path(p).name if p.endswith('.a') else p for p in libraries]
    archive_recipe += '\t$(file >objects.list,' + ' '.join(lists['xedge.elf'] + libraries) + ')\n'
    (PROJECT / 'makefile.targets').write_text(
        '# These prerequisites propagate errors; CDT prefixes its own pre/post recipes with "-".\n'
        '.PHONY: xedge-prepare xedge-output xedge-clean\n'
        'pre-build: xedge-prepare\n'
        'xedge-prepare:\n\tpython "../../../../tools/ide_prepare.py" --output "."\n\n'
        'objects.list: $(OBJS) $(OPTIONAL_TOOL_DEPS)\n' + archive_recipe + '\n'
        'post-build: xedge-output\n'
        'xedge-output:\n\tarm-none-eabi-objcopy -O binary xedge.elf xedge.bin\n'
        '\tarm-none-eabi-size xedge.elf\n\n'
        'clean: xedge-clean\n'
        'xedge-clean:\n\t$(RM) objects.list *.objects libthreadx.a libnetxduo.a libfilex.a liblevelx.a xedge.bin xedge.map\n',
        encoding='utf-8', newline='\n')
    record = {'sources': source_records, 'groups': groups, 'source_count': len(source_records), 'link_libraries': libraries}
    (PROJECT / 'profile.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Generated native project:', len(source_records), 'sources in', len(groups), 'compiler groups')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True, help='Configured CMake build supplying compile_commands.json')
    generate(parser.parse_args().build.resolve())
