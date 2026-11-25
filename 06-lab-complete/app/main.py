"""FastAPI service for the production agent lab."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints
from redis.exceptions import RedisError

from utils.mock_llm import MOCK_RESPONSES, ask as llm_ask

from .auth import verify_api_key
from .config import settings
from .cost_guard import check_budget, record_cost
from .rate_limiter import check_rate_limit
from .redis_client import r, redis_healthy


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "event": record.getMessage(),
                **getattr(record, "fields", {}),
            },
            ensure_ascii=False,
        )


logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def estimate_tokens(text: str) -> int:
    """Use the lab's estimate of two tokens per word."""
    return len(text.split()) * 2


MAX_MOCK_OUTPUT_TOKENS = max(
    estimate_tokens(answer) for answers in MOCK_RESPONSES.values() for answer in answers
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("startup", extra={"fields": {"environment": settings.environment}})
    try:
        yield
    finally:
        r.close()
        logger.info("shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


@app.middleware("http")
async def log_request(request: Request, call_next):
    start = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        logger.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((perf_counter() - start) * 1000, 2),
                }
            },
        )


@app.exception_handler(RedisError)
async def redis_unavailable(_request: Request, _error: RedisError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Redis unavailable"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    input_tokens = estimate_tokens(body.question)
    reservation = check_budget(input_tokens, MAX_MOCK_OUTPUT_TOKENS)
    try:
        answer = llm_ask(body.question)
    except Exception:
        record_cost(reservation, 0, 0)
        raise
    record_cost(reservation, input_tokens, estimate_tokens(answer))
    return {"question": body.question, "answer": answer}
