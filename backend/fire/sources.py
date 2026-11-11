"""Old import path of backend.modules.fire.infrastructure.sources, kept until step 5 (modular-monolith.md section 9)."""
import sys

from ..modules.fire.infrastructure import sources as _impl

sys.modules[__name__] = _impl   # the old name IS the new module: patches and module state stay shared
