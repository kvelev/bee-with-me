from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    postgres_host: str = 'localhost'
    postgres_port: int = 5432
    postgres_db: str = 'rescuer_locator'
    postgres_user: str = 'rescuer'
    postgres_password: str = 'change_me'

    secret_key: str = 'change_me'
    refresh_token_expire_days: int = 7

    serial_port: str = '/dev/ttyUSB0'
    serial_baud: int = 9600

    hid_vendor_id:  int = 0x0ACD
    hid_product_id: int = 0xFAAF

    location_retention_days: int = 90


settings = Settings()
