"""httpx.AsyncClient helpers — per-call timeout enforcement."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)


async def call_upstream(service: str, url: str, payload: dict, timeout_s: float = 5.0):
    """Call one upstream service. Returns an UpstreamResult-shaped dict.

    Per-call timeout via ``httpx.Timeout(timeout_s)`` passed to the
    AsyncClient constructor so the stub's ``.post`` signature stays
    simple (no extra kwargs needed).
    """
    start_ms = time.perf_counter() * 1000

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
            response = await client.post(url, json=payload)

        latency_ms = (time.perf_counter() * 1000) - start_ms
        response.raise_for_status()

        result = {
            "service": service,
            "status": "ok",
            "latency_ms": latency_ms,
            "payload": response.json(),
            "error": None,
        }

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() * 1000) - start_ms
        result = {
            "service": service,
            "status": "timeout",
            "latency_ms": latency_ms,
            "payload": None,
            "error": "Request timed out",
        }

    except Exception as e:
        latency_ms = (time.perf_counter() * 1000) - start_ms
        result = {
            "service": service,
            "status": "error",
            "latency_ms": latency_ms,
            "payload": None,
            "error": str(e),
        }

    logger.debug(
        "upstream_call service=%s status=%s latency_ms=%.1f",
        result["service"],
        result["status"],
        result["latency_ms"],
    )
    return result