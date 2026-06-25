"""Pydantic shapes for the coordinator.

Output shape matches the stretch-thu learner guide:
``{"results": {service_name: response, ...}, "partial": bool, "responded": [service_name, ...]}``.
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AnswerRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class UpstreamResult(BaseModel):
    service: str
    status: Literal["ok", "error", "timeout"]
    latency_ms: float
    payload: Optional[dict] = None
    error: Optional[str] = None


class AnswerResponse(BaseModel):
    """Coordinator response shape — guide §Task 3 contract.

    - ``results`` maps each invoked upstream's service name to its
      response payload (the upstream's JSON body on success, ``null``
      on failure).
    - ``partial`` is ``True`` when at least one upstream failed but at
      least one succeeded; ``False`` when every chosen upstream
      succeeded.
    - ``responded`` lists the service names that returned success
      within the per-call timeout.
    """
    results: Dict[str, Optional[dict]]
    partial: bool
    responded: List[str]
