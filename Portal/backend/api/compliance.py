from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.compliance import ComplianceResult
from backend.services.compliance_engine import ComplianceEngine

router = APIRouter(prefix="/api/compliance", tags=["compliance"])
engine = ComplianceEngine()


class ComplianceRequest(BaseModel):
    ocr_result: dict[str, Any] = Field(..., description="Original OCR response; it is preserved in the derived normalized record")
    validation_profile: str = "e_commerce_product_listing"


@router.post("/evaluate", response_model=ComplianceResult)
def evaluate_compliance(request: ComplianceRequest) -> ComplianceResult:
    try:
        return engine.evaluate(request.ocr_result, request.validation_profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc