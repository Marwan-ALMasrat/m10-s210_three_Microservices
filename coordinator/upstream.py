"""httpx.AsyncClient helpers — per-call timeout enforcement.

Catches a common mistake where learners set the timeout at the session
level (once across the whole AsyncClient lifecycle) instead of per
.get/.post call. The session-level timeout still applies but does not
fire per call, so slow upstreams can starve faster ones.
"""
import time

import httpx


async def call_upstream(service: str, url: str, payload: dict, timeout_s: float = 5.0):
    """Call one upstream service. Returns an UpstreamResult-shaped dict.

    Per-call timeout via `httpx.Timeout(timeout_s)` on `.post`.
    """
    # TODO:
    # 1. Record start_ms = time.perf_counter() * 1000.
    # 2. async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
    #        try POST url with json=payload.
    # 3. On TimeoutException → return {"service", "status": "timeout", ...}.
    # 4. On any other exception → return {"service", "status": "error", "error": str(e), ...}.
    # 5. On success → return {"service", "status": "ok", "payload": r.json(), ...}.
    raise NotImplementedError
