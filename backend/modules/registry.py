"""The module list: one import and one name per module. `main.py` is not edited when a module is added."""
from ..core.modules import ModuleManifest
from .fire.module import manifest as fire_manifest
from .settings.module import manifest as settings_manifest   # `as settings_manifest`: a name equal to the package would replace it
from .sos.module import manifest as sos_manifest
from .tracking.module import manifest as tracking_manifest
from .weather.module import manifest as weather_manifest

MODULES: tuple[ModuleManifest, ...] = (fire_manifest, settings_manifest, weather_manifest, tracking_manifest, sos_manifest)
