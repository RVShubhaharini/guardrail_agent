import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    use_dynamodb: bool = Field(default=False, validation_alias="USE_DYNAMODB")
    dry_run: bool = Field(default=False, validation_alias="DRY_RUN")
    aws_default_region: str = Field(default="us-east-1", validation_alias="AWS_DEFAULT_REGION")
    audit_table: str = Field(default="action_guard_audit", validation_alias="AUDIT_TABLE")
    active_policy_version: str = Field(default="v1", validation_alias="ACTIVE_POLICY_VERSION")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
