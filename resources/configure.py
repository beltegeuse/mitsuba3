from collections import OrderedDict
import json
import re
import sys
import os
import platform
import pathlib

try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO

is_gcc = len(sys.argv) >= 2 and sys.argv[1] == 'GNU'


def write_core_config_cpp(f, enabled, default_variant):
    def w(s):
        if is_gcc:
            # Symbols are always globally visible on GCC
            s = s.replace('MTS_EXPORT_CORE ', '')
            s = s.replace('MTS_EXPORT_RENDER ', '')
            s = s.replace('MTS_EXPORT ', '')
        f.write(s.ljust(79) + ' \\\n')

    f.write('/* This file is automatically generated from "mitsuba.conf" using the script\n')
    f.write('   "resources/configure.py". Please do not attempt to change it manually,\n')
    f.write('   as any changes will be overwritten. The main purpose of this file is to\n')
    f.write('   helper various macros to instantiate multiple variants of Mitsuba. */\n\n')

    f.write('#pragma once\n\n')
    f.write('#include <mitsuba/core/fwd.h>\n')

    enable_jit = False
    enable_ad  = False
    for index, (name, float_, spectrum) in enumerate(enabled):
        enable_jit |= ('cuda' in name) or ('llvm' in name)
        enable_ad  |= ('ad' in name)
    if enable_jit:
        f.write('#include <drjit/jit.h>\n')
    if enable_ad:
        f.write('#include <drjit/autodiff.h>\n')
    f.write('\n')

    f.write('/// List of enabled Mitsuba variants\n')
    w('#define MTS_VARIANTS')
    for index, (name, float_, spectrum) in enumerate(enabled):
        w('    "%s\\n"' % name)
    f.write('\n')

    f.write('/// Default variant to be used by the "mitsuba" executable\n')
    w('#define MTS_DEFAULT_VARIANT "%s"' % default_variant)
    f.write('\n')

    f.write('/// Declare that a "struct" template is to be imported and not instantiated\n')
    w('#define MTS_EXTERN_STRUCT_CORE(Name)')
    for index, (name, float_, spectrum) in enumerate(enabled):
        w('    MTS_EXTERN_CORE template struct MTS_EXPORT_CORE Name<%s, %s>;' % (float_, spectrum))
    f.write('\n')

    f.write('/// Declare that a "class" template is to be imported and not instantiated\n')
    w('#define MTS_EXTERN_CLASS_CORE(Name)')
    for index, (name, float_, spectrum) in enumerate(enabled):
        w('    MTS_EXTERN_CORE template class MTS_EXPORT_CORE Name<%s, %s>;' % (float_, spectrum))
    f.write('\n')

    f.write('/// Declare that a "struct" template is to be imported and not instantiated\n')
    w('#define MTS_EXTERN_STRUCT_RENDER(Name)')
    for index, (name, float_, spectrum) in enumerate(enabled):
        w('    MTS_EXTERN_RENDER template struct MTS_EXPORT_RENDER Name<%s, %s>;' % (float_, spectrum))
    f.write('\n')

    f.write('/// Declare that a "class" template is to be imported and not instantiated\n')
    w('#define MTS_EXTERN_CLASS_RENDER(Name)')
    for index, (name, float_, spectrum) in enumerate(enabled):
        w('    MTS_EXTERN_RENDER template class MTS_EXPORT_RENDER Name<%s, %s>;' % (float_, spectrum))
    f.write('\n')

    f.write('/// Explicitly instantiate all variants of a "struct" template\n')
    w('#define MTS_INSTANTIATE_STRUCT(Name)')
    for index, (name, float_, spectrum) in enumerate(enabled):
        w('    template struct MTS_EXPORT Name<%s, %s>;' % (float_, spectrum))
    f.write('\n')

    f.write('/// Explicitly instantiate all variants of a "class" template\n')
    w('#define MTS_INSTANTIATE_CLASS(Name)')
    for index, (name, float_, spectrum) in enumerate(enabled):
        w('    template class MTS_EXPORT Name<%s, %s>;' % (float_, spectrum))
    f.write('\n')

    f.write('/// Call the variant function "func" for a specific variant "variant"\n')
    w('#define MTS_INVOKE_VARIANT(variant, func, ...)')
    w('    [&]() {')
    for index, (name, float_, spectrum) in enumerate(enabled):
        iff = 'if' if index == 0 else 'else if'
        w('        %s (variant == "%s")' % (iff, name))
        w('            return func<%s, %s>(__VA_ARGS__);' % (float_, spectrum))
    w('        else')
    w('            Throw("Unsupported variant: \\\"%%s\\\". Must be one of %s!", variant);' % (", ".join([v[0] for v in enabled])))
    w('    }()')
    f.write('\n')

    f.write('NAMESPACE_BEGIN(mitsuba)\n')
    f.write('NAMESPACE_BEGIN(detail)\n')
    f.write('/// Convert a <Float, Spectrum> type pair into one of the strings in MTS_VARIANT\n')
    f.write('template <typename Float_, typename Spectrum_> constexpr const char *get_variant() {\n')
    for index, (name, float_, spectrum) in enumerate(enabled):
        f.write('    %sif constexpr (std::is_same_v<Float_, %s> &&\n' % ('else ' if index > 0 else '', float_))
        f.write('    %s              std::is_same_v<Spectrum_, %s>)\n' % ('     ' if index > 0 else '', spectrum))
        f.write('        return "%s";\n' % name)
    f.write('    else\n')
    f.write('        return "";\n')
    f.write('}\n')
    f.write('NAMESPACE_END(detail)\n')
    f.write('NAMESPACE_END(mitsuba)\n')


def write_core_config_python(f, enabled, default_variant):
    f.write('""" This file is automatically generated from "mitsuba.conf" using the script\n')
    f.write('    "resources/configure.py". Please do not attempt to change it manually,\n')
    f.write('    as any changes will be overwritten."""\n\n')

    f.write('PYTHON_EXECUTABLE = r"%s"\n' % sys.executable)
    f.write('MTS_DEFAULT_VARIANT = \'%s\'\n' % default_variant)
    f.write('MTS_VARIANTS = %s\n' % str([v[0] for v in enabled]))


def write_to_file_if_changed(filename, contents):
    '''Writes the given contents to file, only if they do not already match.'''
    if os.path.isfile(filename):
        with open(filename, 'r') as f:
            existing = f.read()
            if existing == contents:
                return False

    with open(filename, 'w') as f:
        f.write(contents)


if __name__ == '__main__':
    with open('mitsuba.conf', 'r') as conf:
        # Strip comments
        s = re.sub(r'(?m)#.*$', '', conf.read())
        # Load JSON
        configurations = json.loads(s)

    # Let's start with some validation
    assert 'enabled' in configurations
    assert isinstance(configurations['enabled'], list)

    # Extract enabled configurations
    enabled = []
    float_types = set()
    for name in configurations['enabled']:
        if name not in configurations:
            raise ValueError('mitsuba.conf: "enabled" refers to an '
                             'unknown configuration "%s"' % name)
        if platform.system() == 'Darwin' and 'cuda' in name:
            continue
        item = configurations[name]
        spectrum = item['spectrum'].replace('Float', item['float'])
        float_types.add(item['float'])
        enabled.append((name, item['float'], spectrum))

    if not enabled:
        raise ValueError('mitsuba.conf: there must be at least one '
                         'enabled build configuration!')

    # Use first configuration
    default_variant = enabled[0][0]
    default_variant_python = configurations.get('python-default', '')

    if default_variant not in configurations['enabled']:
        raise ValueError('mitsuba.conf: the "default" mode is not part of '
                         'the "enabled" list!')

    if default_variant_python != '' and \
            default_variant_python not in configurations['enabled']:
        raise ValueError('mitsuba.conf: the "python-default" mode is not '
                         'part of the "enabled" list!')

    pathlib.Path("include/mitsuba/core").mkdir(parents=True, exist_ok=True)
    fname = 'include/mitsuba/core/config.h'
    output = StringIO()
    write_core_config_cpp(output, enabled, default_variant)
    write_to_file_if_changed(fname, output.getvalue())

    pathlib.Path("python/mitsuba").mkdir(parents=True, exist_ok=True)
    fname = 'python/mitsuba/config.py'
    output = StringIO()
    write_core_config_python(output, enabled, default_variant_python)
    write_to_file_if_changed(fname, output.getvalue())

    for index, (name, float_, spectrum) in enumerate(enabled):
        print('%s|%s|%s' % (name, float_, spectrum),
              end=';' if index < len(enabled) - 1 else '')
