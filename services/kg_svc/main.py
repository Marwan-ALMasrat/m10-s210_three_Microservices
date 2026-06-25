"""Mock downstream KG service."""
from fastapi import FastAPI

app = FastAPI(title="kg_svc (mock)")


@app.post("/kg/query")
async def kg_query(payload: dict):
    return {"cypher": "MATCH (n) RETURN n", "rows": [], "count": 0, "service": "kg_svc"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
