from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

ComplianceStatus = Literal["COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE", "NEEDS_MANUAL_VERIFICATION"]
FieldStatus = Literal["PASS", "FAIL", "PARTIAL", "NEEDS_MANUAL_VERIFICATION", "NOT_DETECTED"]


class NormalizedField(BaseModel):
    value: Any = None
    detected: bool = False
    confidence: float = Field(0, ge=0, le=1)
    source: str = "ocr"


class NormalizedOCRResult(BaseModel):
    document_id: str
    product_type: str = "unknown"
    package_type: str = "retail"
    raw_text: str = ""
    raw_ocr_result: dict[str, Any] = Field(default_factory=dict)
    fields: dict[str, NormalizedField] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldResult(BaseModel):
    status: FieldStatus
    value: Any = None
    confidence: float = 0
    missing: list[str] = Field(default_factory=list)
    explanation: str = ""


class Evidence(BaseModel):
    requirement: str
    ocr_evidence: str = "Not detected by OCR"
    validation: str
    result: str


class RuleResult(BaseModel):
    rule_id: str
    rule_name: str
    status: ComplianceStatus
    score: float = 0
    required_fields: dict[str, FieldResult] = Field(default_factory=dict)
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    evidence_details: list[Evidence] = Field(default_factory=list)
    recommended_action: str = ""


class ComplianceSummary(BaseModel):
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    partial: int = 0
    manual_verification: int = 0
    not_applicable: int = 0
    total_checks: int = 0


class ComplianceResult(BaseModel):
    success: bool = True
    document_id: str
    ruleset_id: str
    ruleset_version: str
    validation_profile: str
    overall_status: ComplianceStatus
    compliance_score: float = Field(ge=0, le=100)
    summary: ComplianceSummary
    rule_results: list[RuleResult] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    audit: dict[str, Any]