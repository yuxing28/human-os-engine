"""
Human-OS Engine - 配置管理

使用 Pydantic Settings 从环境变量加载配置。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # NVIDIA NIM（支持多个 Key 轮询）
    nvidia_api_keys: str = ""  # 逗号分隔的多个 API Key
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "deepseek-ai/deepseek-r1"

    # DeepSeek 官方 API（用于话术生成，更稳定）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_official_api_key: str = ""
    deepseek_official_base_url: str = "https://api.deepseek.com/v1"
    deepseek_official_model: str = "deepseek-chat"
    llm_provider: str = ""

    # 应用配置
    app_name: str = "Human-OS Engine"
    app_version: str = "3.0"
    debug: bool = False
    admin_api_key: str = ""

    # LangGraph 配置
    max_recursion_limit: int = 25

    # 输出限制
    max_output_length: int = 300  # 话痨拦截器阈值

    @field_validator("debug", mode="before")
    @classmethod
    def _normalize_debug(cls, value):
        """兼容历史环境变量中的 release/prod/debug 等字符串写法。"""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "debug", "dev", "development"}:
            return True
        if text in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return False

    def get_api_keys(self) -> list[str]:
        """获取 NVIDIA API Key 列表"""
        if not self.nvidia_api_keys:
            return []
        return [k.strip() for k in self.nvidia_api_keys.split(",") if k.strip()]

    @property
    def env_file_path(self) -> str:
        return str(ENV_FILE_PATH)


@lru_cache()
def get_settings() -> Settings:
    """获取配置（单例）"""
    return Settings()


settings = get_settings()
