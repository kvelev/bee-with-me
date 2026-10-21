"""Stub `python -m pip` for the start-script tests: installs nothing, logs the call.

BWM_STUB_PIP_FAIL=1: every call writes an error to stderr and exits 1 (nothing installed, no internet).
BWM_STUB_PIP_OFFLINE_FAIL=1: only the local check (`--no-index`) fails, as when a package is missing
from the venv and the local wheel folder but the internet is up.
"""

import os
import sys

with open(os.environ['BWM_STUB_LOG'], 'a', encoding='utf-8') as log:
    log.write('pip ' + ' '.join(sys.argv[1:]) + '\n')
if os.environ.get('BWM_STUB_PIP_FAIL') == '1':
    print('ERROR: stub pip: No matching distribution found for stubpkg', file=sys.stderr)
    sys.exit(1)
if os.environ.get('BWM_STUB_PIP_OFFLINE_FAIL') == '1' and '--no-index' in sys.argv:
    print('ERROR: stub pip: No matching distribution found for stubpkg (no index)', file=sys.stderr)
    sys.exit(1)
sys.exit(0)
