# m10-s210 — Multi-Service Coordinator (Stretch Thu)

## Architecture

```
                        ┌─────────────────┐
  POST /answer ────────▶│   coordinator   │
                        │   :8000         │
                        └────────┬────────┘
                                 │ POST /classify
                        ┌────────▼────────┐
                        │ classifier_svc  │
                        │   :8001         │
                        └────────┬────────┘
                    routes[]     │
          ┌──────────────────────┼───────────────┐
          │                      │               │
  ┌───────▼──────┐  ┌────────────▼─────┐  ┌─────▼──────┐
  │   nlp_svc   │  │    kg_svc        │  │  rag_svc   │
  │  :8002      │  │   :8003          │  │  :8004     │
  │  /extract   │  │  /kg/query       │  │ /rag/answer│
  └─────────────┘  └──────────────────┘  └────────────┘
```

**Flow:** `POST /answer` → classifier decides which backend(s) → concurrent fan-out → aggregate → `AnswerResponse`

Partial failure: if one upstream 503s or times out, coordinator returns `200` with `"partial": true` and lists only the services that responded in `responded`.

---

## Setup

```bash
git clone https://github.com/<your-username>/m10-s210.git
cd m10-s210
git checkout -b stretch-10-thu-coordinator
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running the Stack

```bash
docker compose up -d --build
```

Wait ~30 s for all healthchecks to pass, then verify:

```bash
docker compose ps
```

All services should show `(healthy)`.

---

## Demo — End-to-End Routing

### KG-shaped question (routes to kg_svc only)
```bash
curl -s -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "find Sichuan recipes with ginger"}' | python -m json.tool
```

Expected: `responded: ["kg_svc"]`, `partial: false`

### RAG-shaped question (routes to rag_svc only)
```bash
curl -s -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "how do I cook this dish"}' | python -m json.tool
```

Expected: `responded: ["rag_svc"]`, `partial: false`

### Hybrid question (routes to both)
```bash
curl -s -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "find recipes that prep ginger"}' | python -m json.tool
```

Expected: `responded: ["kg_svc", "rag_svc"]`, `partial: false`

---

## Partial Failure Test

Kill rag_svc mid-run:

```bash
docker compose stop rag_svc
```

Send a hybrid question:

```bash
curl -s -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "find recipes that prep ginger"}' | python -m json.tool
```

Expected response (200, not 503):

```json
{
  "results": {
    "kg_svc": { "cypher": "MATCH (n) RETURN n", "rows": [], "count": 0, "service": "kg_svc" },
    "rag_svc": null
  },
  "partial": true,
  "responded": ["kg_svc"]
}
```

Restore:

```bash
docker compose start rag_svc
```

---

## Running Unit Tests (no Docker needed)

```bash
pip install pyyaml pytest pytest-asyncio
pytest tests/test_coordinator.py -v
```

---

## PR Description

### Coordinator Design

The coordinator is a thin orchestration layer that sits between the client and three domain microservices. On each `POST /answer` call it first asks `classifier_svc` which downstream service(s) are relevant, then fans out concurrently using `asyncio.gather` with per-call `httpx.AsyncClient` timeouts (5 s for NLP and KG, 10 s for RAG since generation dominates). Each upstream result is tagged with `service`, `status`, `latency_ms`, and `payload`. The aggregation step separates successes from failures: if at least one upstream responded and at least one failed, the coordinator returns `200` with `partial: true` and lists only the responding services in `responded`. Only when all upstreams fail does the coordinator return `503`. One structured log line is emitted per inbound request showing which upstreams were called, which responded, and total latency — formatted for Module 11's log reader.

### Microservice Split — Cost / Benefit

Splitting the monolithic Lab backend into three containers (nlp_svc, kg_svc, rag_svc) bought independent deployability and failure isolation: killing rag_svc does not take down entity extraction or graph queries, and each service can be scaled or updated independently. It also forced explicit contracts between services — each has its own Pydantic models, healthcheck, and requirements.txt, which surfaces hidden coupling. The cost is real: shared concerns (healthz, structured errors, Pydantic base models) are duplicated across three files instead of imported from one place, the Compose topology is more complex, and inter-service latency replaces what were previously in-process function calls. For a production workload where the three backends have very different compute profiles (NLP is CPU-bound, RAG is GPU-bound) the split pays clearly; for a prototype, the monolith is faster to ship and easier to debug.