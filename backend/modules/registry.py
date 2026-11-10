"""The module list: one import and one name per module. `main.py` is not edited when a module is added."""
from ..core.modules import ModuleManifest
from .settings.module import manifest as settings_manifest   # `as settings_manifest`: a name equal to the package would replace it

MODULES: tuple[ModuleManifest, ...] = (settings_manifest,)
