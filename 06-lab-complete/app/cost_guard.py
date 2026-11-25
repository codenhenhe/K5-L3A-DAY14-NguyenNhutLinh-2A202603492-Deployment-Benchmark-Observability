"""Shared daily LLM budget with atomic reservation and settlement."""

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException

from .config import settings
from .redis_client import r

NANOUSD_PER_USD = 1_000_000_000
INPUT_NANOUSD_PER_TOKEN = 150
OUTPUT_NANOUSD_PER_TOKEN = 600
BUDGET_KEY_TTL_SECONDS = 2 * 24 * 60 * 60

# Money is stored as integer billionths of a dollar so small charges are exact.
_RESERVE = """
local current = redis.call("GET", KEYS[1])
local spent = tonumber(current or "0")
local requested = tonumber(ARGV[1])
local budget = tonumber(ARGV[2])
if spent >= budget or spent + requested > budget then
    return 0
end
redis.call("INCRBY", KEYS[1], ARGV[1])
if not current then
    redis.call("EXPIRE", KEYS[1], ARGV[3])
end
return 1
"""


@dataclass(frozen=True)
class Reservation:
    key: str
    nanousd: int


def check_budget(input_tokens: int, max_output_tokens: int) -> Reservation:
    """Reserve the maximum charge before invoking the mock LLM."""
    cost = input_tokens * INPUT_NANOUSD_PER_TOKEN + max_output_tokens * OUTPUT_NANOUSD_PER_TOKEN
    day = datetime.now(timezone.utc).date().isoformat()
    key = f"agent:daily-cost:{day}"
    budget = int(settings.daily_budget_usd * NANOUSD_PER_USD)
    if not r.eval(_RESERVE, 1, key, cost, budget, BUDGET_KEY_TTL_SECONDS):
        raise HTTPException(status_code=402, detail="Daily budget exceeded")
    return Reservation(key, cost)


def record_cost(reservation: Reservation, input_tokens: int, output_tokens: int) -> float:
    """Settle the actual charge against the same day's reservation."""
    cost = input_tokens * INPUT_NANOUSD_PER_TOKEN + output_tokens * OUTPUT_NANOUSD_PER_TOKEN
    r.incrby(reservation.key, cost - reservation.nanousd)
    return cost / NANOUSD_PER_USD
