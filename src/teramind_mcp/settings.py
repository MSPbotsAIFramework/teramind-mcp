"""Non-secret server configuration.

Credentials never appear here — they only ever travel as per-request
headers (see auth.py). This class holds HTTP bind settings only.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8080


def get_settings() -> Settings:
    return Settings()
