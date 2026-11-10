"""The public face of the `settings` module: the only file other modules may import.

Events carry IDs only (DP-02); the settings table has one row, so `SettingsChanged` has no fields.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SettingsChanged:
    """A settings change was saved; whoever reacts reads the row itself."""
