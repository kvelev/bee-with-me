"""Old import path of backend.modules.weather.http, kept until step 5 (modular-monolith.md section 9)."""
import sys

from ..modules.weather import http as _impl

sys.modules[__name__] = _impl   # the old name IS the new module: patches and module state stay shared
