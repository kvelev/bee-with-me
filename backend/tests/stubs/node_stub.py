"""Stub `node` for the start-script tests: `node -v` prints BWM_STUB_NODE_VERSION (default v24.11.0).

`node -e <check>` runs the version checks of the scripts against that version: a check naming `=== 23`
refuses majors 23 and 25, any other check refuses versions below 22.12. BWM_STUB_NODE_CHECK, when set,
overrides the exit code of every check.
"""

import os
import sys

version = os.environ.get('BWM_STUB_NODE_VERSION', 'v24.11.0')
if sys.argv[1:2] == ['-v']:
    print(version)
    sys.exit(0)
if 'BWM_STUB_NODE_CHECK' in os.environ:
    sys.exit(int(os.environ['BWM_STUB_NODE_CHECK']))
major, minor = (int(part) for part in version.lstrip('v').split('.')[:2])
script = sys.argv[2] if sys.argv[1:2] == ['-e'] and len(sys.argv) > 2 else ''
if '=== 23' in script:
    sys.exit(1 if major in (23, 25) else 0)
sys.exit(0 if (major, minor) >= (22, 12) else 1)
