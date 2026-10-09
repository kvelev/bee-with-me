import re
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, BaseModel, Field, field_validator

KNOWN_ROLES = ('admin', 'rescuer', 'viewer')


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    postgres_host: str = 'localhost'
    postgres_port: int = 5432
    postgres_db: str = 'rescuer_locator'
    postgres_user: str = 'rescuer'
    postgres_password: str = 'change_me'

    secret_key: str = 'change_me'
    # Password of the `admin` account created on an empty database. Empty = the historical 'admin'
    # (field laptops); any internet-facing install must set it before its first start.
    initial_admin_password: str = ''
    refresh_token_expire_days: int = 7
    access_token_expire_minutes: int = 60

    # Dev-only simulation endpoints (POST /api/test/simulate) write fabricated positions
    # into location_events. Off by default so a field deployment can't be polluted.
    enable_test_endpoints: bool = False

    # GET /api/locations/live ignores devices whose last fix is older than this, so
    # trackers from a previous operation don't linger on the map as ghosts.
    live_position_max_age_hours: int = 24

    serial_port: str = '/dev/ttyUSB0'
    serial_baud: int = 9600

    hid_vendor_id:  int = 0x0ACD
    hid_product_id: int = 0xFAAF

    location_retention_days: int = 90

    offline_maps_password: str = 'change_me'

    # OpenWeatherMap key, used only server-side by routers/weather.py (the browser never sees it).
    # VITE_OWM_API_KEY is the name older .env files use from when the browser called OWM directly.
    owm_api_key: str = Field('', validation_alias=AliasChoices('owm_api_key', 'vite_owm_api_key'))

    # Which roles may log in (POST /api/auth/login and /refresh), comma-separated. The owner's rule is
    # admin-only; widen it with LOGIN_ROLES=admin,rescuer. Other users keep their account and role.
    login_roles: str = 'admin'

    # Pending migrations are applied only after a backup of THIS database in its current state:
    # the backup scripts write this marker next to the dump (start.ps1/start.sh back up into
    # data/backups). Resolved relative to the project folder, like uploads/.
    backup_marker_path: Path = Path(__file__).resolve().parent.parent / 'data' / 'backups' / 'last-backup.json'
    # Developers on dev data only (e.g. uvicorn --reload): migrate without that backup, with a WARNING.
    allow_migrate_without_backup: bool = False
    # Per-file lock_timeout of the migration runner: a migration that cannot get its table locks in
    # this time fails the start-up with a clear error instead of waiting (and queueing writers) forever.
    migration_lock_timeout: str = '5s'

    @field_validator("migration_lock_timeout")
    def validate_lock_timeout(cls, v):
        match = re.fullmatch(r'(\d{1,10})(ms|s|min)', v)
        if not match:
            raise ValueError("migration_lock_timeout must look like 200ms, 5s or 1min")
        milliseconds = int(match.group(1)) * {'ms': 1, 's': 1000, 'min': 60_000}[match.group(2)]
        # 0 disables lock_timeout (undoing the fail-loud guard); more than an hour is a typo, not a wait
        if not 0 < milliseconds <= 3_600_000:
            raise ValueError("migration_lock_timeout must be more than 0 and at most 1h")
        return v

    @field_validator("login_roles")
    def validate_login_roles(cls, v):
        roles = [part.strip().lower() for part in v.split(',') if part.strip()]
        unknown = [r for r in roles if r not in KNOWN_ROLES]
        if not roles or unknown:
            raise ValueError("login_roles must be a comma-separated list of: " + ", ".join(KNOWN_ROLES))
        return ','.join(dict.fromkeys(roles))

    @property
    def login_role_set(self) -> frozenset[str]:
        return frozenset(part.strip() for part in self.login_roles.split(',') if part.strip())

    @field_validator("backup_marker_path")
    def resolve_marker_path(cls, v):
        # a relative BACKUP_MARKER_PATH is relative to the project folder, not to the working directory
        return v if v.is_absolute() else Path(__file__).resolve().parent.parent / v

    @field_validator("hid_vendor_id", "hid_product_id", mode="before")
    def parse_int(cls, v):
        if isinstance(v, str):
            return int(v, 16) if v.startswith("0x") else int(v)
        return v

    @field_validator("hid_vendor_id", "hid_product_id")
    def validate_range(cls, v, info):
        if not (0 <= v <= 0xFFFF):
            raise ValueError(f"{info.field_name} must be 0–65535")
        return v


settings = Settings()
