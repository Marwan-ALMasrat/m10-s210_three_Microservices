"""Mock downstream NLP service.

In the live stretch repo, this is replaced with the decomposed nlp_svc
that wraps the Lab's /extract endpoint. Here it ships as a minimal mock
the coordinator can fan out against while the learner authors the real
service body.
"""
from fastapi import FastAPI

app = FastAPI(title="nlp_svc (mock)")


@app.post("/extract")
async def extract(payload: dict):
    return {"entities": [], "service": "nlp_svc"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
