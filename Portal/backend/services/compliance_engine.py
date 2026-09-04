from __future__ import annotations

import json
import re
import uuid
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.models.compliance import ComplianceResult, ComplianceSummary, Evidence, FieldResult, NormalizedField, NormalizedOCRResult, RuleResult

RULESET_PATH = Path(__file__).resolve().parents[1] / "rules" / "legal_metrology_rules_2011.json"
ENGINE_VERSION = "1.0.0"
CONFIDENCE_THRESHOLD = 0.80
ALIASES = {
    "manufacturer_packer_importer_details": ["manufacturer", "packer", "importer", "manufactured by", "packed by"],
    "country_of_origin": ["country of origin", "made in", "origin"],
    "common_generic_name_of_commodity": ["product name", "commodity", "generic name", "rice", "sugar", "flour"],
    "net_quantity": ["net quantity", "net qty", "net weight", "net wt"],
    "month_and_year_of_manufacture_or_packing": ["date of manufacture", "manufactured", "mfg", "packed on", "packing date"],
    "maximum_retail_price_mrp": ["maximum retail price", "mrp", "m.r.p", "rs.", "rs ", "₹"],
    "unit_sale_price": ["unit sale price", "price per", "/kg", "/ g", "/g", "/litre", "/l"],
    "consumer_care_details": ["consumer care", "customer care", "helpline", "toll free"],
    "name_and_address_of_manufacturer_or_packer": ["manufacturer", "packer", "address"],
    "identity_of_commodity": ["product name", "commodity", "generic name"],
    "total_number_of_retail_packages_or_net_quantity": ["net quantity", "number of packages", "retail packages"],
}


def load_ruleset(path: Path = RULESET_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _text_and_confidence(ocr_result: dict[str, Any]) -> tuple[str, float]:
    text = str(ocr_result.get("full_text", ""))
    detections = ocr_result.get("detections") or []
    confidence = sum(float(item.get("confidence", 0)) for item in detections) / len(detections) if detections else 0
    return text, confidence


def normalize_ocr_result(ocr_result: dict[str, Any], document_id: str | None = None) -> NormalizedOCRResult:
    """Create a derived view of OCR data; the supplied OCR dictionary is never mutated."""
    raw_text, average_confidence = _text_and_confidence(ocr_result)
    lowered = raw_text.lower()
    product_type = str(ocr_result.get("product_type") or ocr_result.get("category") or "packaged_commodity").lower()
    package_type = str(ocr_result.get("package_type") or "retail").lower()
    fields: dict[str, NormalizedField] = {}
    for field_name, aliases in ALIASES.items():
        match = next((alias for alias in aliases if alias in lowered), None)
        value = None
        if match:
            line = next((line.strip() for line in raw_text.splitlines() if match in line.lower()), raw_text)
            value = line
        fields[field_name] = NormalizedField(value=value, detected=match is not None, confidence=average_confidence)

    mrp_line = next((line.strip() for line in raw_text.splitlines() if re.search(r"maximum\s+retail\s+price|m\.?r\.?p\.?", line, re.I)), None)
    if mrp_line:
        fields["maximum_retail_price_mrp"] = NormalizedField(value=mrp_line, detected=True, confidence=average_confidence)
    elif len(re.findall(r"(?:₹|Rs\.?|INR)\s*[0-9]+(?:\.[0-9]{1,2})?", raw_text, re.I)) != 1 or re.search(r"unit\s+sale|price\s+per|/kg|/g|/l", raw_text, re.I):
        fields["maximum_retail_price_mrp"] = NormalizedField()

    care_match = re.search(r"(?:consumer|customer)\s+care\s*[:\-]?\s*(.+)", raw_text, re.I)
    if care_match:
        care_text = care_match.group(1)
        phone = re.search(r"(?:\+91[\s-]?)?[0-9][0-9\s-]{6,14}[0-9]", care_text)
        email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", care_text)
        fields["consumer_care_details"] = NormalizedField(
            value={
                "name": care_text.split()[0] if care_text.split() else None,
                "address": care_text,
                "telephone_number": phone.group(0) if phone else None,
                "email_address": email.group(0) if email else None,
            },
            detected=True,
            confidence=average_confidence,
        )

    supplied_fields = ocr_result.get("fields") or {}
    for name, supplied in supplied_fields.items():
        if isinstance(supplied, dict):
            fields[name] = NormalizedField(value=supplied.get("value", supplied), detected=bool(supplied.get("detected", supplied.get("value") is not None)), confidence=float(supplied.get("confidence", 0)))
        else:
            fields[name] = NormalizedField(value=supplied, detected=supplied is not None, confidence=average_confidence)

    metadata = {key: ocr_result.get(key) for key in ("instrument_category", "last_verification_date", "physical_seal_verified", "certificate_of_verification", "total_package_weight", "wrapper_packaging_weight") if ocr_result.get(key) is not None}
    return NormalizedOCRResult(document_id=document_id or str(ocr_result.get("document_id") or f"DOC-{uuid.uuid4().hex[:8].upper()}"), product_type=product_type, package_type=package_type, raw_text=raw_text, raw_ocr_result=dict(ocr_result), fields=fields, metadata=metadata)


def _field(normalized: NormalizedOCRResult, name: str) -> NormalizedField:
    return normalized.fields.get(name, NormalizedField())


def _field_result(field: NormalizedField, label: str) -> FieldResult:
    if not field.detected:
        return FieldResult(status="FAIL", explanation=f"{label} was not detected by OCR; physical absence is not confirmed.")
    if field.confidence < CONFIDENCE_THRESHOLD:
        return FieldResult(status="NEEDS_MANUAL_VERIFICATION", value=field.value, confidence=field.confidence, explanation=f"{label} was detected with low OCR confidence.")
    return FieldResult(status="PASS", value=field.value, confidence=field.confidence, explanation=f"{label} was detected by OCR.")


def _mrp_result(field: NormalizedField, requirement: str) -> tuple[FieldResult, Evidence]:
    if not field.detected:
        result = FieldResult(status="FAIL", explanation="MRP was not detected by OCR; physical absence is not confirmed.")
        return result, Evidence(requirement=requirement, validation="No INR amount or MRP label detected", result="FAIL")
    if field.confidence < CONFIDENCE_THRESHOLD:
        result = FieldResult(status="NEEDS_MANUAL_VERIFICATION", value=field.value, confidence=field.confidence, explanation="MRP OCR confidence is below the verification threshold.")
        return result, Evidence(requirement=requirement, ocr_evidence=str(field.value), validation="Low-confidence OCR", result="NEEDS_MANUAL_VERIFICATION")
    value = str(field.value)
    amounts = re.findall(r"(?:₹|Rs\.?|INR)\s*([0-9]+(?:\.[0-9]{1,2})?)", value, re.I)
    has_label = bool(re.search(r"(?:maximum\s+retail\s+price|m\.?r\.?p\.?)", value, re.I))
    if not amounts:
        result = FieldResult(status="FAIL", value=value, explanation="The detected MRP does not contain a valid INR amount.")
        return result, Evidence(requirement=requirement, ocr_evidence=value, validation="INR amount not parseable", result="FAIL")
    if len(amounts) > 1:
        result = FieldResult(status="NEEDS_MANUAL_VERIFICATION", value=value, confidence=field.confidence, explanation="OCR detected multiple possible MRP values.")
        return result, Evidence(requirement=requirement, ocr_evidence=value, validation="Multiple amounts detected", result="NEEDS_MANUAL_VERIFICATION")
    if not has_label:
        result = FieldResult(status="NEEDS_MANUAL_VERIFICATION", value=value, confidence=field.confidence, explanation="An amount was detected, but the required MRP wording was not detected.")
        return result, Evidence(requirement=requirement, ocr_evidence=value, validation="Valid amount; MRP wording absent", result="NEEDS_MANUAL_VERIFICATION")
    result = FieldResult(status="PASS", value={"detected_value": value, "normalized_value": float(amounts[0]), "currency": "INR"}, confidence=field.confidence, explanation="Valid INR MRP amount and MRP wording detected.")
    return result, Evidence(requirement=requirement, ocr_evidence=value, validation="Valid INR amount and MRP keyword", result="PASS")


def _rule_result(rule: dict[str, Any], normalized: NormalizedOCRResult) -> RuleResult:
    rule_id = rule["rule_id"]
    fields: dict[str, FieldResult] = {}
    evidence: list[str] = []
    details: list[Evidence] = []
    if rule_id == "LMPC-R6-MANDATORY-DECLARATIONS":
        for name in rule["required_fields"]:
            current = _field(normalized, name)
            if name == "maximum_retail_price_mrp":
                result, detail = _mrp_result(current, "Maximum Retail Price")
                fields[name], details = result, details + [detail]
            elif name == "consumer_care_details":
                care = current.value if isinstance(current.value, dict) else {}
                missing = [key for key in rule["validations"]["consumer_care_fields"] if not care.get(key)]
                status = "PARTIAL" if current.detected and missing else ("FAIL" if not current.detected else "PASS")
                fields[name] = FieldResult(status=status, value=current.value, confidence=current.confidence, missing=missing, explanation="Consumer-care details are incomplete." if missing else "Consumer-care details detected.")
            else:
                fields[name] = _field_result(current, name.replace("_", " ").title())
            evidence.append(f"{name}: {fields[name].status}")
        statuses = [item.status for item in fields.values()]
        status = "NON_COMPLIANT" if "FAIL" in statuses else ("NEEDS_MANUAL_VERIFICATION" if "NEEDS_MANUAL_VERIFICATION" in statuses else ("PARTIALLY_COMPLIANT" if "PARTIAL" in statuses else "COMPLIANT"))
        passed = sum(item.status == "PASS" for item in fields.values())
        score = round(passed / len(fields) * 100, 2) if fields else 0
        missing = [name for name, item in fields.items() if item.status in ("FAIL", "PARTIAL")]
        return RuleResult(rule_id=rule_id, rule_name="Mandatory Declarations", status=status, score=score, required_fields=fields, explanation="Mandatory declaration requirements are not fully satisfied." if status != "COMPLIANT" else "All mandatory declarations were detected and validated.", evidence=evidence, evidence_details=details, recommended_action="Verify the physical package and add or correct missing declarations if absent.",)
    if rule_id == "LMPC-R11-NET-QUANTITY-EXCLUSION":
        net = normalized.metadata.get("net_quantity") or normalized.fields.get("net_quantity", NormalizedField()).value
        total = normalized.metadata.get("total_package_weight")
        wrapper = normalized.metadata.get("wrapper_packaging_weight")
        if total is None or wrapper is None or net is None:
            return RuleResult(rule_id=rule_id, rule_name="Net Quantity Exclusion", status="NEEDS_MANUAL_VERIFICATION", explanation="Required weight evidence was not detected by OCR.", evidence=["Net, total, or wrapper weight evidence unavailable"], recommended_action="Verify the package weights and statistical tolerances manually.")
        expected = float(total) - float(wrapper)
        passed = abs(float(net) - expected) < 0.0001
        return RuleResult(rule_id=rule_id, rule_name="Net Quantity Exclusion", status="COMPLIANT" if passed else "NON_COMPLIANT", score=100 if passed else 0, explanation="Net quantity equals package weight less wrapper weight." if passed else "Net quantity does not equal package weight less wrapper weight.", evidence=[f"Expected net quantity: {expected}"], recommended_action="Check the declared net quantity and applicable statistical tolerances.")
    if rule_id == "LMPC-R24-WHOLESALE-DECLARATIONS":
        names = rule["required_fields"]
        for name in names:
            fields[name] = _field_result(_field(normalized, name), name.replace("_", " ").title())
        statuses = [item.status for item in fields.values()]
        status = "NON_COMPLIANT" if "FAIL" in statuses else ("NEEDS_MANUAL_VERIFICATION" if "NEEDS_MANUAL_VERIFICATION" in statuses else "COMPLIANT")
        return RuleResult(rule_id=rule_id, rule_name="Wholesale Declarations", status=status, score=round(sum(item.status == "PASS" for item in fields.values()) / len(fields) * 100, 2), required_fields=fields, explanation="Wholesale declaration requirements are not fully satisfied." if status != "COMPLIANT" else "Wholesale declarations detected.", evidence=[f"{name}: {fields[name].status}" for name in names], recommended_action="Verify wholesale package declarations on the physical package.")
    if rule_id == "LMGEN-R12-VERIFICATION-INTERVALS":
        raw_date = normalized.metadata.get("last_verification_date")
        if not raw_date:
            return RuleResult(rule_id=rule_id, rule_name="Verification Intervals", status="NEEDS_MANUAL_VERIFICATION", explanation="Last verification date was not detected by OCR.", recommended_action="Verify the instrument certificate and date manually.")
        category = str(normalized.metadata.get("instrument_category", "")).lower()
        months = 24 if any(word in category for word in ("capacity", "length", "weight")) else 12
        verified = datetime.fromisoformat(str(raw_date)).date()
        expiry_month = verified.month - 1 + months
        expiry = date(verified.year + expiry_month // 12, expiry_month % 12 + 1, min(verified.day, monthrange(verified.year + expiry_month // 12, expiry_month % 12 + 1)[1]))
        passed = date.today() <= expiry
        return RuleResult(rule_id=rule_id, rule_name="Verification Intervals", status="COMPLIANT" if passed else "NON_COMPLIANT", score=100 if passed else 0, explanation=f"Verification expires on {expiry.isoformat()}." if passed else f"Verification expired on {expiry.isoformat()}.", evidence=[f"Last verification: {verified.isoformat()}", f"Period: {months} months"], recommended_action="Renew the instrument verification.")
    if rule_id == "LMGEN-R14-STAMPING-SEALING":
        if not normalized.metadata.get("physical_seal_verified") or not normalized.metadata.get("certificate_of_verification"):
            return RuleResult(rule_id=rule_id, rule_name="Stamping and Sealing", status="NEEDS_MANUAL_VERIFICATION", explanation="OCR does not provide sufficient evidence that the physical seal and verification certificate are present.", evidence=["Physical verification evidence unavailable from OCR"], recommended_action="Inspect the physical seal, verification mark, and certificate.")
        return RuleResult(rule_id=rule_id, rule_name="Stamping and Sealing", status="COMPLIANT", score=100, explanation="Physical verification evidence was supplied for review.", evidence=["Seal and certificate evidence supplied"], recommended_action="Retain the verification evidence with the audit record.")
    return RuleResult(rule_id=rule_id, rule_name=rule_id, status="NOT_APPLICABLE", explanation="No evaluator is registered for this rule.")


class ComplianceEngine:
    def __init__(self, ruleset_path: Path = RULESET_PATH):
        self.ruleset_path = ruleset_path

    def evaluate(self, ocr_result: dict[str, Any], validation_profile: str) -> ComplianceResult:
        ruleset = load_ruleset(self.ruleset_path)
        normalized = normalize_ocr_result(ocr_result)
        profile = ruleset.get("validation_profiles", {}).get(validation_profile)
        if profile is None:
            raise ValueError(f"Unknown validation profile: {validation_profile}")
        if normalized.product_type in {"unknown", "unrelated", "other"}:
            results = [RuleResult(rule_id="PROFILE", rule_name="Validation Profile", status="NOT_APPLICABLE", explanation="The detected object is not a supported Legal Metrology product.")]
        else:
            all_rules = {rule["rule_id"]: rule for framework in ruleset["frameworks"] for rule in framework["rules"]}
            results = []
            for rule_id in profile.get("evaluate_rules", []):
                if rule_id == "LMPC-R24-WHOLESALE-DECLARATIONS" and normalized.package_type != "wholesale":
                    results.append(RuleResult(rule_id=rule_id, rule_name="Wholesale Declarations", status="NOT_APPLICABLE", explanation="The package type is retail, so the wholesale rule does not apply."))
                else:
                    results.append(_rule_result(all_rules[rule_id], normalized))
        summary = ComplianceSummary(total_rules=len(results), total_checks=sum(len(item.required_fields) or 1 for item in results))
        for item in results:
            if item.status == "COMPLIANT": summary.passed += 1
            elif item.status == "NON_COMPLIANT": summary.failed += 1
            elif item.status == "PARTIALLY_COMPLIANT": summary.partial += 1
            elif item.status == "NEEDS_MANUAL_VERIFICATION": summary.manual_verification += 1
            else: summary.not_applicable += 1
        checks = [field.status for rule in results for field in rule.required_fields.values()] or [rule.status for rule in results]
        score = round(sum(status == "PASS" or status == "COMPLIANT" for status in checks) / len(checks) * 100, 2) if checks else 0
        if summary.failed: overall = "NON_COMPLIANT"
        elif summary.partial: overall = "PARTIALLY_COMPLIANT"
        elif summary.manual_verification: overall = "NEEDS_MANUAL_VERIFICATION"
        elif summary.not_applicable == summary.total_rules: overall = "NOT_APPLICABLE"
        else: overall = "COMPLIANT"
        missing = [f"{rule.rule_name}: {name}" for rule in results for name, field in rule.required_fields.items() if field.status in ("FAIL", "PARTIAL")]
        return ComplianceResult(document_id=normalized.document_id, ruleset_id=ruleset["ruleset_id"], ruleset_version=ruleset["version"], validation_profile=validation_profile, overall_status=overall, compliance_score=score, summary=summary, rule_results=results, missing_fields=missing, warnings=["OCR confidence is evidence quality, not legal compliance."], recommendations=[rule.recommended_action for rule in results if rule.recommended_action], audit={"evaluated_at": datetime.now(timezone.utc).isoformat(), "engine_version": ENGINE_VERSION, "ocr_result_version": ocr_result.get("version", "unknown")})