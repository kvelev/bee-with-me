from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    postgres_host: str = 'localhost'
    postgres_port: int = 5432
    postgres_db: str = 'rescuer_locator'
    postgres_user: str = 'rescuer'
    postgres_password: str = 'change_me'

    secret_key: str = 'change_me'
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    serial_port: str = '/dev/ttyUSB0'
    serial_baud: int = 9600


settings = Settings()
