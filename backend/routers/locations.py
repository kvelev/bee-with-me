"""Old import path of the tracking and sos HTTP modules, kept until step 5.

One old module became two, so this is not a sys.modules alias: it passes on the names below and nothing else.
A patch of a name here would hit this copy, not the module (test_no_test_patches_a_name_of_the_locations_shim).
"""
from fastapi import APIRouter

from ..modules.sos.http import open_sos_alerts, resolve_sos
from ..modules.sos.http import router as _sos_router
from ..modules.tracking.http import device_history, live_positions, location_trail, settings
from ..modules.tracking.http import router as _tracking_router

router = APIRouter()
router.include_router(_tracking_router)
router.include_router(_sos_router)
