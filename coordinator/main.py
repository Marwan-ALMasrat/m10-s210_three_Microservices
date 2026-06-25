"""Multi-service coordinator — Stretch Thu (Honors Track).

The coordinator exposes a single POST /answer endpoint. On each call it:
1. Calls the classifier service to identify which downstream service(s)
   should answer the question.
2. Fans out to the selected service(s) via httpx.AsyncClient with a
   per-call 5-second timeout.
3. Aggregates the responses and returns a single AnswerResponse.
4. If any upstream returns a 5xx or times out, the coordinator returns
   200 with `partial: true` and a per-service attribution payload —
   never a 5xx that would lose the working upstream's response.
"""
from fastapi import FastAPI

from .models import AnswerRequest, AnswerResponse

app = FastAPI(title="Stretch Thu — Multi-Service Coordinator")


@app.post("/answer")
async def answer(req: AnswerRequest):
    """Classify → fan out → aggregate → respond.

    Returns AnswerResponse. `partial: true` iff one or more upstreams
    failed or timed out.
    """
    # TODO: set response_model=AnswerResponse on the decorator above.
    # TODO: ask the classifier which downstream services should answer.
    # TODO: fan out to each selected service over httpx.AsyncClient with
    #       a per-call timeout (longer for the generation service).
    # TODO: collect each upstream's outcome and record which services
    #       responded successfully.
    # TODO: set `partial` when at least one upstream failed and at least
    #       one succeeded.
    # TODO: return AnswerResponse with `results`, `partial`, and
    #       `responded` populated.
    raise NotImplementedError


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
