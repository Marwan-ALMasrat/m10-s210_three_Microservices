"""Multi-service coordinator — Stretch Thu (Honors Track).

The coordinator exposes a single POST /answer endpoint. On each call it:
1. Calls the classifier service to identify which downstream service(s)
   should answer the question.
2. Fans out to the selected service(s) via httpx.AsyncClient with a
   per-call timeout (5 s default; 10 s for rag_svc).
3. Aggregates the responses and returns a single AnswerResponse.
4. If any upstream returns a 5xx or times out, the coordinator returns
   200 with `partial: true` and a per-service attribution payload —
   never a 5xx that would lose the working upstream's response.
"""
import asyncio
import logging
import os

from fastapi import FastAPI, HTTPException

from .models import AnswerRequest, AnswerResponse, UpstreamResult
from .upstream import call_upstream

logger = logging.getLogger(__name__)

app = FastAPI(title="Stretch Thu — Multi-Service Coordinator")

# Service URL map — can be overridden via env vars in Compose
CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier_svc:8001/classify")

SERVICE_URLS: dict[str, str] = {
    "nlp_svc": os.getenv("NLP_SVC_URL", "http://nlp_svc:8002/extract"),
    "kg_svc": os.getenv("KG_SVC_URL", "http://kg_svc:8003/kg/query"),
    "rag_svc": os.getenv("RAG_SVC_URL", "http://rag_svc:8004/rag/answer"),
}

# RAG gets a longer timeout because generation dominates
TIMEOUT_MAP: dict[str, float] = {
    "nlp_svc": 5.0,
    "kg_svc": 5.0,
    "rag_svc": 10.0,
}


@app.post("/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest) -> AnswerResponse:
    """Classify → fan out → aggregate → respond.

    Returns AnswerResponse. `partial: true` iff one or more upstreams
    failed or timed out but at least one succeeded.
    """
    import time
    request_start = time.perf_counter()

    # ── Step 1: classify ────────────────────────────────────────────────
    clf_result = await call_upstream(
        service="classifier_svc",
        url=CLASSIFIER_URL,
        payload={"question": req.question},
        timeout_s=5.0,
    )

    if clf_result["status"] != "ok":
        raise HTTPException(
            status_code=503,
            detail={
                "error": "classifier_svc unavailable",
                "status": clf_result["status"],
            },
        )

    clf_body = clf_result.get("payload") or clf_result.get("result") or {}
    routes = clf_body.get("routes", [])
    selected_services = [r["service"] for r in routes if r["service"] in SERVICE_URLS]

    # Fallback: if classifier returns nothing we know, route to rag_svc
    if not selected_services:
        selected_services = ["rag_svc"]

    # ── Step 2: fan out concurrently ────────────────────────────────────
    tasks = [
        call_upstream(
            service=svc,
            url=SERVICE_URLS[svc],
            payload={"question": req.question},
            timeout_s=TIMEOUT_MAP.get(svc, 5.0),
        )
        for svc in selected_services
    ]
    upstream_results: list[dict] = await asyncio.gather(*tasks)

    # ── Step 3: aggregate ───────────────────────────────────────────────
    results: dict[str, dict | None] = {}
    responded: list[str] = []

    for res in upstream_results:
        svc = res["service"]
        if res["status"] == "ok":
            results[svc] = res.get("payload") or res.get("result")
            responded.append(svc)
        else:
            results[svc] = None

    partial = len(responded) > 0 and len(responded) < len(selected_services)

    # ── Step 4: all upstreams failed → 503 ─────────────────────────────
    if len(responded) == 0:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "all upstream services failed",
                "attempted": selected_services,
            },
        )

    total_latency_ms = (time.perf_counter() - request_start) * 1000

    logger.info(
        "request_complete question_len=%d upstreams_called=%s responded=%s "
        "partial=%s total_latency_ms=%.1f",
        len(req.question),
        selected_services,
        responded,
        partial,
        total_latency_ms,
    )

    return AnswerResponse(results=results, partial=partial, responded=responded)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}