"""Old import path of backend.core.ws, kept until step 5 (modular-monolith.md section 9)."""
import sys

from .core import ws as _impl

sys.modules[__name__] = _impl   # the old name IS the new module: patches and module state stay shared
