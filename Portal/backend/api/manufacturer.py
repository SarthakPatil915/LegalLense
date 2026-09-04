"""Manufacturer-owned products and immutable self-check revisions."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.api.auth import manufacturer_user
from backend.api.ocr import run_ocr
from backend.database import get_database
from backend.ocr.schemas import OCRResult

router = APIRouter(prefix="/api/manufacturer", tags=["manufacturer"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductRequest(BaseModel):
    productName: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)


def public_product(product: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in product.items() if key != "_id" and key != "manufacturerId"}


def compliance_report(result: OCRResult) -> dict[str, Any]:
    """Produce the shared report shape until the legal rule engine is connected."""
    text = result.full_text or ""
    checks = [
        ("Product name", bool(text), "Label text must identify the product", "Legal declaration requirements"),
        ("Net quantity", any(token in text.lower() for token in (" g", " kg", " ml", " l", "unit")), "Net quantity must be declared", "Legal Metrology Packaged Commodities Rules"),
        ("MRP", "mrp" in text.lower() or "₹" in text, "MRP inclusive of taxes must be declared", "Legal Metrology declaration requirements"),
        ("Manufacturer", any(token in text.lower() for token in ("manufactured", "manufactur", "address")), "Manufacturer name and address must be declared", "Legal Metrology declaration requirements"),
    ]
    fields = []
    for name, detected, expected, citation in checks:
        fields.append({"field": name, "status": "compliant" if detected else "needs_fix", "detectedValue": text if detected else "Not detected", "expectedRequirement": expected, "ruleCitation": citation, "confidence": 0.9 if detected else 0.45, "suggestion": "No change required" if detected else "Add this declaration clearly before printing."})
    issues = [field for field in fields if field["status"] != "compliant"]
    return {"overallResult": "compliant" if not issues else "needs_fix", "fields": fields, "issues": issues, "confidence": round(sum(field["confidence"] for field in fields) / len(fields), 2)}


@router.get("/products")
def list_products(user: dict[str, Any] = Depends(manufacturer_user)):
    products = get_database().products.find({"manufacturerId": user["_id"]}).sort("updatedAt", -1)
    return {"success": True, "items": [public_product(product) for product in products]}


@router.post("/products")
def create_product(payload: ProductRequest, user: dict[str, Any] = Depends(manufacturer_user)):
    db = get_database()
    now = utcnow()
    product = {"productId": f"PRD-{uuid.uuid4().hex[:12].upper()}", "manufacturerId": user["_id"], "productName": payload.productName.strip(), "sku": payload.sku.strip(), "description": payload.description.strip(), "latestStatus": None, "latestScore": None, "createdAt": now, "updatedAt": now}
    db.products.insert_one(product)
    db.history.insert_one({"userId": user["_id"], "manufacturerId": user["_id"], "actionType": "product_created", "title": "Product created", "description": product["productName"], "documentId": product["productId"], "createdAt": now})
    return {"success": True, "product": public_product(product)}


@router.post("/self-check")
async def create_self_check(
    file: UploadFile = File(...),
    product_id: str = Form(""),
    product_name: str = Form(""),
    user: dict[str, Any] = Depends(manufacturer_user),
):
    db = get_database()
    product = db.products.find_one({"productId": product_id, "manufacturerId": user["_id"]}) if product_id else None
    if product_id and product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    ocr_response = await run_ocr(file)
    if ocr_response.status_code != 200:
        return ocr_response
    result = OCRResult.model_validate(json.loads(ocr_response.body))
    report = compliance_report(result)
    now = utcnow()
    resolved_product_name = product["productName"] if product else product_name.strip() or result.image
    if product is None:
        product = {"productId": f"PRD-{uuid.uuid4().hex[:12].upper()}", "manufacturerId": user["_id"], "productName": resolved_product_name, "sku": "PENDING", "description": "", "createdAt": now}
        db.products.insert_one(product)
    version = db.productRevisions.count_documents({"productId": product["productId"], "manufacturerId": user["_id"]}) + 1
    revision = {"revisionId": f"REV-{uuid.uuid4().hex[:12].upper()}", "productId": product["productId"], "manufacturerId": user["_id"], "version": version, "imageReference": result.image, "ocrResult": result.model_dump(), "complianceResult": report, "issues": report["issues"], "suggestions": [issue["suggestion"] for issue in report["issues"]], "confidence": report["confidence"], "createdAt": now}
    db.productRevisions.insert_one(revision)
    score = round((1 - len(report["issues"]) / len(report["fields"])) * 100)
    db.products.update_one({"productId": product["productId"], "manufacturerId": user["_id"]}, {"$set": {"latestStatus": report["overallResult"], "latestScore": score, "updatedAt": now}})
    db.history.insert_one({"userId": user["_id"], "manufacturerId": user["_id"], "actionType": "self_check_performed", "title": "Self-check completed", "description": f"Revision {version} for {resolved_product_name}", "documentId": revision["revisionId"], "createdAt": now})
    return {"success": True, "revision": {key: value for key, value in revision.items() if key != "manufacturerId" and key != "_id"}}


@router.get("/revisions")
def list_revisions(user: dict[str, Any] = Depends(manufacturer_user)):
    revisions = get_database().productRevisions.find({"manufacturerId": user["_id"]}, {"_id": 0, "manufacturerId": 0}).sort("createdAt", -1)
    return {"success": True, "items": list(revisions)}
