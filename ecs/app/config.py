from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dynamodb_table_name: str = "collision_report_dev"
    aws_region: str = "us-west-2"


settings = Settings()
