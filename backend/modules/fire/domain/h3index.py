"""H3 cell index (resolution 8) for stored hotspots — for future heatmaps; the alarm never uses it.

A missing or broken h3 wheel must never stop a field laptop from starting: the column is then NULL.
"""

import logging

logger = logging.getLogger(__name__)

try:
    import h3 as _h3
except Exception as exc:  # noqa: BLE001 — any import failure, including a broken binary wheel
    _h3 = None
    logger.warning('h3 unavailable (%s); fire_hotspots.h3_r8 will be NULL', exc)


def h3_r8(latitude: float, longitude: float) -> int | None:
    if _h3 is None:
        return None
    # H3 indexes never set the top bit, so they fit a signed BIGINT.
    return int(_h3.latlng_to_cell(latitude, longitude, 8), 16)
