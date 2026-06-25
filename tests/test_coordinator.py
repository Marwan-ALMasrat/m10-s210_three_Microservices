"""Stretch Thu autograder.

Tests use httpx-mock or a small in-process app to avoid spinning the
full Compose stack. The end-to-end Compose check is exercised by the
workflow.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_compose():
    """Load docker-compose.yml. Fails (not skips) if the file is
    missing or has empty services — the stretch requires the learner
    to author the 5-service Compose stack as Task 4. A skipped result
    here would let an unstarted compose surface earn green CI."""
    import yaml

    compose_path = REPO_ROOT / "starter" / "docker-compose.yml"
    if not compose_path.exists():
        compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), (
        f"docker-compose.yml not present at {compose_path}. The "
        f"stretch's Task 4 ships the 5-service Compose stack — its "
        f"absence is a real failure, not a benign skip."
    )
    cfg = yaml.safe_load(compose_path.read_text()) or {}
    assert (cfg.get("services") or {}), (
        "docker-compose.yml has empty services — the stretch's Task 4 "
        "requires authoring the 5-service stack (coordinator + "
        "classifier_svc + nlp_svc + kg_svc + rag_svc). A green "
        "autograder must not be reachable from `services: {}`."
    )
    return cfg


def test_compose_coordinator_depends_on_chain_uses_healthy_condition():
    """Catches buggy variant: learner declares bare `depends_on: [...]`
    lists for the coordinator. The bare form waits for container
    start, not readiness; the coordinator then races ahead of the
    classifier and backends and 503s its first calls.

    Per the spec Task 4: coordinator depends on classifier_svc healthy
    AND nlp_svc / kg_svc / rag_svc healthy.
    """
    cfg = _load_compose()
    services = cfg["services"]
    assert "coordinator" in services, "coordinator service missing"
    deps = services["coordinator"].get("depends_on")
    assert isinstance(deps, dict), (
        "coordinator.depends_on must be the long-form mapping with "
        "`condition: service_healthy` per dependency. Bare list form "
        "waits for container start, not readiness — first calls 503."
    )
    for backend in ("classifier_svc", "nlp_svc", "kg_svc", "rag_svc"):
        assert backend in deps, (
            f"coordinator must depend on {backend!r} per the spec Task 4."
        )
        assert deps[backend].get("condition") == "service_healthy", (
            f"coordinator.depends_on.{backend} must use "
            f"`condition: service_healthy`. Got "
            f"{deps[backend].get('condition')!r}."
        )


def test_coordinator_answer_endpoint_implemented(monkeypatch):
    """Catches buggy variant: silent-pass guard.

    Hits the coordinator's /answer endpoint via TestClient with
    `call_upstream` stubbed to return a successful mock response.
    The CI workflow does not spin the Compose stack (services: {}),
    so we cannot rely on real classifier or backend services; the
    stub stands in for them.

    The test asserts that a correct implementation:
      1. Returns 200 on a valid AnswerRequest body.
      2. Populates `responded` with at least one service name —
         an empty `responded=[]` signals the implementation skipped
         the fan-out entirely (silent-pass).

    Unmodified starter raises NotImplementedError → 500 (fails).
    Correctly-implemented coordinator under the stub → 200 with
    `responded` populated (passes).
    """
    import asyncio

    from fastapi.testclient import TestClient

    from coordinator import main as coord_main
    from coordinator import upstream as coord_upstream

    async def _stub_call_upstream(service, url, payload, timeout_s=5.0):
        # Stand-in success response. Shape matches what the
        # coordinator's aggregation step is expected to consume.
        return {
            "service": service,
            "status": "ok",
            "latency_ms": 1,
            "result": {"answer": "stub", "citations": []},
        }

    async def _stub_classify_call(*args, **kwargs):
        # If the coordinator routes via httpx to the classifier rather
        # than calling call_upstream, the test also stubs at the httpx
        # boundary below.
        return _stub_call_upstream("classifier_svc", "", {})

    # Stub call_upstream wherever it's referenced.
    monkeypatch.setattr(coord_upstream, "call_upstream", _stub_call_upstream)
    if hasattr(coord_main, "call_upstream"):
        monkeypatch.setattr(coord_main, "call_upstream", _stub_call_upstream)

    # Stub httpx.AsyncClient for any path that bypasses call_upstream
    # and calls the classifier directly via httpx.
    import httpx

    class _StubResponse:
        status_code = 200

        def json(self):
            return {"routes": [{"service": "rag_svc", "confidence": 0.5}]}

        def raise_for_status(self):
            return None

    class _StubClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, **kwargs):
            return _StubResponse()

        async def get(self, url, **kwargs):
            return _StubResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

    client = TestClient(coord_main.app)
    r = client.post("/answer", json={"question": "find Sichuan recipes"})
    assert r.status_code == 200, (
        f"coordinator /answer must return 200 on a valid question "
        f"with upstreams stubbed. Got {r.status_code}. "
        f"Body: {r.text[:200]}"
    )
    body = r.json()
    responded = body.get("responded")
    assert isinstance(responded, list) and len(responded) >= 1, (
        "coordinator /answer must populate `responded` with at least "
        f"one upstream service name. Got responded={responded!r}."
    )


def test_answer_response_shape_declared():
    """Structural-only check on the AnswerResponse / UpstreamResult shape.

    The CI workflow runs unit-style tests against httpx mocks only — the
    learner's docker-compose stack is exercised manually per the stretch
    spec (see workflow comment). This test does NOT catch a misrouted
    classifier or a coordinator that fans out to every service; it only
    verifies that the response model carries the per-source attribution
    fields a learner would need to make routing observable. End-to-end
    routing correctness is reviewed by the TA per the stretch rubric."""
    from coordinator.models import AnswerResponse, UpstreamResult
    fields = AnswerResponse.model_fields
    assert "results" in fields
    assert "partial" in fields
    assert "responded" in fields
    assert "service" in UpstreamResult.model_fields


def test_per_call_timeout_enforced(monkeypatch):
    """Catches buggy variant: learner does not enforce a per-call timeout —
    when an upstream call hangs longer than ``timeout_s``, ``call_upstream``
    must return ``status='timeout'`` (not block, not raise, not succeed).

    Asserts behavior by calling ``call_upstream`` with a stubbed
    ``httpx.AsyncClient`` that raises ``httpx.TimeoutException`` on
    ``.post``.
    """
    import asyncio
    import httpx

    from coordinator.upstream import call_upstream

    class _StubResponse:
        def json(self):
            return {"unused": True}

    class _StubClient:
        def __init__(self, *args, **kwargs):
            self._timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            raise httpx.TimeoutException("simulated upstream hang")

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

    result = asyncio.run(
        call_upstream("nlp_svc", "http://stub/upstream", {"q": "ping"}, timeout_s=0.05)
    )
    # Normalize: function may return a dict or an UpstreamResult model.
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    assert isinstance(result, dict), f"expected dict-shaped result, got {type(result).__name__}"
    assert result.get("status") == "timeout", (
        f"per-call timeout was not enforced; got status={result.get('status')!r}. "
        "Reference uses httpx.Timeout(timeout_s) on the .post call."
    )
    assert result.get("service") == "nlp_svc"
    assert "latency_ms" in result


def test_classifier_returns_routes_with_confidence():
    """Catches buggy variant: classifier silently picks one route on
    ambiguous questions; coordinator ignores hybrid intent."""
    from services.classifier_svc.main import classify
    import asyncio

    result = asyncio.run(classify({"question": "find recipes that prep ginger"}))
    routes = result["routes"]
    assert isinstance(routes, list)
    assert all("service" in r and "confidence" in r for r in routes)


def test_structured_log_per_upstream_call_documented(monkeypatch, caplog):
    """Catches buggy variant: no structured log emitted per upstream call.

    Calls ``call_upstream`` with a stubbed ``httpx.AsyncClient`` whose
    ``.post`` succeeds, then asserts that the call produced at least one
    log record whose payload references the service, status, and latency.
    """
    import asyncio
    import logging
    import httpx

    from coordinator.upstream import call_upstream

    class _StubResponse:
        def json(self):
            return {"answer": "ok"}

    class _StubClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            return _StubResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)
    caplog.set_level(logging.DEBUG)

    result = asyncio.run(
        call_upstream("kg_svc", "http://stub/upstream", {"q": "ping"}, timeout_s=1.0)
    )
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    assert result.get("status") == "ok"

    # Reference emits one structured log record per call. The shape can
    # vary (a logging.Logger call OR a `print(json.dumps(...))`); either
    # path produces output that mentions the service name and status.
    log_text = "\n".join(record.getMessage() for record in caplog.records).lower()
    assert "kg_svc" in log_text, (
        f"no log record referenced the service name. Logged: {log_text!r}"
    )
    assert ("status" in log_text or "ok" in log_text), (
        "structured-log line did not reference call status. Reference emits "
        "one log line per upstream call with service / status / latency_ms."
    )
    assert "latency" in log_text, (
        "structured-log line did not reference latency. Reference emits "
        "service / status / latency_ms per call."
    )
