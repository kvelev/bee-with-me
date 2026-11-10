"""Request and response shapes of the settings API. Pure: pydantic only, no web and no database."""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, model_validator

# Strict: JSON strings ("false", "5") and 0/1 for booleans are 422, never coerced (BP-02).
StrictLat = Annotated[float, Field(strict=True, ge=-90, le=90)]
StrictLon = Annotated[float, Field(strict=True, ge=-180, le=180)]
StrictInt = Annotated[int, Field(strict=True)]


class HQIn(BaseModel):
    hq_latitude: StrictLat
    hq_longitude: StrictLon


class HQPatch(BaseModel):
    """PUT /api/settings/hq: both numbers (set) or both null (clear)."""
    hq_latitude: StrictLat | None
    hq_longitude: StrictLon | None

    @model_validator(mode='after')
    def _hq_both_or_neither(self):
        if (self.hq_latitude is None) != (self.hq_longitude is None):
            raise ValueError('hq_latitude and hq_longitude must both be set or both be empty')
        return self


class SettingsIn(BaseModel):
    hq_latitude: StrictLat | None = None
    hq_longitude: StrictLon | None = None
    is_hq_alarm_enabled: StrictBool
    is_rescuer_alarm_enabled: StrictBool
    hq_radius_m: Annotated[StrictInt, Field(ge=100, le=100_000)]
    rescuer_radius_m: Annotated[StrictInt, Field(ge=100, le=100_000)]
    alarm_max_age_hours: Annotated[StrictInt, Field(ge=1, le=168)]
    repeat_minutes: Annotated[StrictInt, Field(ge=1, le=60)]
    is_rescuer_photo_on_map_enabled: StrictBool

    @model_validator(mode='after')
    def _hq_both_or_neither(self):
        if (self.hq_latitude is None) != (self.hq_longitude is None):
            raise ValueError('hq_latitude and hq_longitude must both be set or both be empty')
        return self


class SettingsUpdate(SettingsIn):
    expected_updated_at: datetime   # the updated_at the client last saw (optimistic concurrency)


class SettingsOut(SettingsIn):
    updated_at: datetime
