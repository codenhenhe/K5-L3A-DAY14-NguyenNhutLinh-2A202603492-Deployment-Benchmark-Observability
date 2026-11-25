"""Runtime settings supplied through environment variables."""

import os
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class Settings:
    port: int
    environment: str
    agent_api_key: str = field(repr=False)
    redis_url: str
    rate_limit_per_minute: int
    daily_budget_usd: Decimal

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        if self.rate_limit_per_minute < 1:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be positive")
        if not self.daily_budget_usd.is_finite() or self.daily_budget_usd < 0:
            raise ValueError("DAILY_BUDGET_USD must be finite and non-negative")


settings = Settings(
    port=int(os.getenv("PORT") or "8000"),
    environment=os.getenv("ENVIRONMENT", "development"),
    agent_api_key=os.getenv("AGENT_API_KEY", ""),
    redis_url=os.getenv("REDIS_URL") or "redis://localhost:6379/0",
    rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")),
    daily_budget_usd=Decimal(os.getenv("DAILY_BUDGET_USD", "1")),
)
