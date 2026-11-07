"""Decode json/jsonb columns that asyncpg hands back as text.

The pool has no json codec (backend/fire/models.py decodes its own jsonb), so a
`json_agg(...)` column arrives as a JSON string. Clients expect a real array.
"""
import json
import logging

logger = logging.getLogger(__name__)


def decode_json_columns(row, *columns: str) -> dict:
    """dict(row) with the named columns decoded from JSON text to Python values.

    Already-decoded values pass through; NULL becomes []; undecodable text becomes []
    (one bad cell must not fail the whole listing).
    """
    out = dict(row)
    for col in columns:
        if col not in out:
            continue
        val = out[col]
        if val is None:
            out[col] = []
        elif isinstance(val, (str, bytes, bytearray)):
            try:
                out[col] = json.loads(val)
            except ValueError:
                logger.warning('Column %s is not valid JSON; returning an empty list', col)
                out[col] = []
    return out
