"""
HTTP layer for OCR. This module owns request validation, temp-file handling,
and response shaping ONLY - all actual OCR inference is delegated to the
existing, already-tested PaddleOCRService. No OCR/PaddleOCR logic is
duplicated here.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from backend.database import get_database
from backend.api.auth import official_user
from backend.ocr.paddle_ocr_service import OCRInitializationError, PaddleOCRService
from backend.ocr.schemas import OCRError, OCRResult
from backend.services.compliance_engine import ComplianceEngine

logger = logging.getLogger("legallense.api.ocr")

router = APIRouter()

# One shared service instance: PaddleOCRService caches its underlying
# PaddleOCR engine internally, so the (slow) model load happens once per
# process, not once per request.
_service = PaddleOCRService()
_compliance_engine = ComplianceEngine()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB safety cap for local dev

# Uploads are written into the OS temp dir under their own subfolder so we
# never write into (or serve from) the project tree, and never trust a
# client-supplied path.
_UPLOAD_TMP_DIR = Path(tempfile.gettempdir()) / "legallense_ocr_uploads"
_UPLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)


def _error_response(status_code: int, image: str, code: str, message: str) -> JSONResponse:
    result = OCRResult(success=False, image=image, error=OCRError(code=code, message=message))
    return JSONResponse(status_code=status_code, content=result.model_dump())


def _scan_document(result: OCRResult, product_name: str, category: str, manufacturer: str, file_name: str) -> dict[str, Any]:
    return {
        "id": f"SCN-{uuid.uuid4().hex[:12].upper()}",
        "productName": product_name or file_name,
        "category": category or "General",
        "manufacturer": manufacturer or "Not specified",
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "score": None,
        "caseId": None,
        "fileName": file_name,
        "findings": [],
        "ocr": result.model_dump(),
    }


def _public_scan(scan: dict[str, Any]) -> dict[str, Any]:
    """Remove Mongo internals and make ownership IDs JSON serializable."""
    public = {key: value for key, value in scan.items() if key != "_id"}
    if public.get("userId") is not None:
        public["userId"] = str(public["userId"])
    return public


@router.post("/api/ocr", response_model=OCRResult)
async def run_ocr(file: Optional[UploadFile] = File(None)):
    """Accept one image (JPG/JPEG/PNG/WEBP), run it through PaddleOCRService, return OCRResult JSON."""

    if file is None or not file.filename:
        logger.warning("OCR request received with no file attached")
        return _error_response(400, "", "missing_file", "No file was uploaded")

    # Path(...).name strips any directory component the client might send
    # (e.g. "../../etc/passwd.jpg") - only the base filename is ever used,
    # and only for display; it is never used to build a filesystem path.
    original_name = Path(file.filename).name
    suffix = Path(original_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        logger.warning("Rejected unsupported file type '%s' for %s", suffix, original_name)
        return _error_response(
            400, original_name, "unsupported_file_type",
            f"Unsupported file type '{suffix}'. Supported: {sorted(ALLOWED_EXTENSIONS)}",
        )

    contents = await file.read()
    if not contents:
        logger.warning("Rejected empty upload for %s", original_name)
        return _error_response(400, original_name, "empty_upload", "Uploaded file is empty")

    if len(contents) > MAX_UPLOAD_BYTES:
        logger.warning("Rejected oversized upload for %s (%d bytes)", original_name, len(contents))
        return _error_response(
            400, original_name, "file_too_large",
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )

    # Random server-generated filename - never derived from client input.
    tmp_path = _UPLOAD_TMP_DIR / f"{uuid.uuid4().hex}{suffix}"

    try:
        tmp_path.write_bytes(contents)
        logger.info("Saved upload '%s' (%d bytes) to temp file for OCR", original_name, len(contents))

        result = _service.run(str(tmp_path))
        # Swap the temp filename back out for the original, client-facing name,
        # and scrub the server-side temp path out of any error message so no
        # internal filesystem detail reaches the browser.
        result.image = original_name
        result.image_path = None
        if result.error is not None:
            result.error.message = result.error.message.replace(str(tmp_path), original_name)

        status_code = 200 if result.success else 422
        logger.info(
            "OCR request for '%s' complete: success=%s detections=%d",
            original_name, result.success, result.detection_count,
        )
        return JSONResponse(status_code=status_code, content=result.model_dump())

    except OCRInitializationError as exc:
        logger.exception("PaddleOCR engine failed to initialize")
        return _error_response(503, original_name, "engine_init_failed", "OCR engine failed to initialize")

    except Exception:
        logger.exception("Unexpected error while processing OCR request for %s", original_name)
        return _error_response(500, original_name, "internal_error", "Unexpected server error during OCR processing")

    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            logger.warning("Failed to clean up temp file %s", tmp_path, exc_info=True)


@router.post("/api/scans")
async def create_scan(
    file: Optional[UploadFile] = File(None),
    product_name: str = Form(""),
    category: str = Form("General"),
    manufacturer: str = Form("Not specified"),
    user: dict[str, Any] = Depends(official_user),
):
    """Run OCR and persist the original scan record in MongoDB."""
    response = await run_ocr(file)
    if response.status_code != 200:
        return response

    result = OCRResult.model_validate(response.body and __import__("json").loads(response.body))
    if not result.success:
        return response

    compliance = _compliance_engine.evaluate(
        result.model_dump(),
        "pos_hardware_audit" if category.strip().lower() in {"weighing_instrument", "instrument", "pos hardware"} else "e_commerce_product_listing",
    )
    scan = _scan_document(result, product_name.strip(), category.strip(), manufacturer.strip(), result.image)
    status_map = {
        "COMPLIANT": "compliant",
        "NON_COMPLIANT": "flagged",
        "PARTIALLY_COMPLIANT": "partial",
        "NEEDS_MANUAL_VERIFICATION": "manual_review",
        "NOT_APPLICABLE": "not_applicable",
    }
    scan.update({
        "userId": user["_id"],
        "success": True,
        "image": result.image,
        "full_text": result.full_text,
        "detections": [d.model_dump() for d in result.detections],
        "detection_count": result.detection_count,
        "preprocessing_applied": result.preprocessing_applied,
        "error": None,
        "compliance": compliance.model_dump(),
        "status": status_map[compliance.overall_status],
        "score": compliance.compliance_score,
    })
    get_database().scans.insert_one(scan)
    get_database().history.insert_one({
        "userId": user["_id"],
        "actionType": "scan_uploaded",
        "title": "Product label uploaded",
        "description": f"OCR scan created for {scan['productName']}.",
        "documentId": scan["id"],
        "metadata": {"fileName": result.image, "category": scan["category"]},
        "createdAt": datetime.now(timezone.utc),
    })
    logger.info("Persisted scan %s to MongoDB", scan["id"])
    return _public_scan(scan)


@router.get("/api/scans")
def list_scans(user: dict[str, Any] = Depends(official_user)):
    """Return persisted scans newest first."""
    scans = get_database().scans.find({"userId": user["_id"]}, {"_id": 0}).sort("date", -1)
    return [_public_scan(scan) for scan in scans]


@router.get("/api/scans/{scan_id}")
def get_scan(scan_id: str, user: dict[str, Any] = Depends(official_user)):
    """Return one persisted scan by its public ID."""
    scan = get_database().scans.find_one({"id": scan_id, "userId": user["_id"]}, {"_id": 0})
    if scan is None:
        return JSONResponse(status_code=404, content={"detail": "Scan not found"})
    return _public_scan(scan)


@router.get("/api/cases")
def list_cases(user: dict[str, Any] = Depends(official_user)):
    """Return persisted cases newest first."""
    cases = get_database().cases.find({"userId": user["_id"]}, {"_id": 0}).sort("date", -1)
    return [{**case, "userId": str(case["userId"])} if case.get("userId") is not None else case for case in cases]
