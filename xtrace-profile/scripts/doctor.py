#!/usr/bin/env python3
"""Report pinned Xtrace environment readiness; does not launch GPU kernels."""
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import sys
from pathlib import Path


def main():
    from xtrace_local.splice import NATIVE_SHA
    report = {'python': sys.version, 'platform': platform.platform(),
              'machine': platform.machine(), 'libc': platform.libc_ver(),
              'expected_native_sha256': NATIVE_SHA, 'checks': {}}
    checks = report['checks']
    checks['supported_python'] = sys.version_info[:2] == (3, 12)
    checks['supported_platform'] = sys.platform == 'linux' and platform.machine() == 'x86_64'
    try:
        report['gwatch_version'] = importlib.metadata.version('gwatch')
        checks['pinned_version'] = report['gwatch_version'] == '0.0.35'
        spec = importlib.util.find_spec('gwatch')
        native = Path(spec.origin).parent / 'libgwatch_dark_cuda128_x86_64.so'
        report['native_path'] = str(native)
        report['native_sha256'] = hashlib.sha256(native.read_bytes()).hexdigest()
        checks['native_identity'] = report['native_sha256'] == NATIVE_SHA
        if checks['native_identity'] and checks['pinned_version']:
            from gwatch.cuda.binary import Cubin
            from gwatch.cuda.xtrace._schema import SassTraceSite, TraceSchema_SASS
            import gwatch.cuda.xtrace._sass_instrumenter as upstream
            checks['adapter_imports'] = callable(upstream.TraceInstrumenter_SASS)
        else:
            checks['adapter_imports'] = False
    except Exception as exc:
        checks['backend_ready'] = False
        report['backend_error'] = f'{type(exc).__name__}: {exc}'
    try:
        import numpy
        report['numpy_version'] = numpy.__version__
        checks['raw_decoder_dependency'] = True
    except ImportError as exc:
        checks['raw_decoder_dependency'] = False
        report['decoder_error'] = str(exc)
    report['status'] = 'environment_ready_runtime_validation_required' if all(checks.values()) else 'environment_incomplete'
    report['scope'] = 'Import and identity checks only; not a driver/GPU/launch correctness test.'
    print(json.dumps(report, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
