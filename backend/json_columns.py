"""Old import path of backend.core.json_columns, kept until step 5 (modular-monolith.md section 9)."""
import sys

from .core import json_columns as _impl

sys.modules[__name__] = _impl   # the old name IS the new module: patches and module state stay shared
