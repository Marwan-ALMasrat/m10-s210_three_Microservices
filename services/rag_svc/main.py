"""Mock downstream RAG service."""
from fastapi import FastAPI

app = FastAPI(title="rag_svc (mock)")


@app.post("/rag/answer")
async def rag_answer(payload: dict):
    return {
        "answer": "A mocked grounded answer [1].",
        "citations": [{"chunk_id": 1, "score": 0.9}],
        "confidence": 0.9,
        "service": "rag_svc",
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
