"""MongoDB-backed authentication, OTP verification, profile, and history APIs."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import bcrypt
import requests
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from backend.database import get_database

router = APIRouter(prefix="/api/auth", tags=["auth"])
SESSION_COOKIE = "legallense_session"
OTP_MINUTES = 10
SESSION_DAYS = 7


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def otp_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user["_id"]),
        "fullName": user["fullName"],
        "email": user["email"],
        "role": user.get("role", "manufacturer"),
        "companyName": user.get("companyName", ""),
        "emailVerified": bool(user.get("emailVerified", False)),
        "createdAt": user.get("createdAt"),
    }


def send_email(to_email: str, subject: str, html: str) -> None:
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip()
    if not api_key or not sender_email:
        raise HTTPException(status_code=503, detail="Email service is not configured")
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"accept": "application/json", "api-key": api_key, "content-type": "application/json"},
        json={"sender": {"email": sender_email, "name": os.getenv("BREVO_SENDER_NAME", "LegalLense")}, "to": [{"email": to_email}], "subject": subject, "htmlContent": html},
        timeout=10,
    )
    if response.status_code in (401, 403):
        raise HTTPException(status_code=503, detail="Brevo API key was rejected. Generate a new Brevo API key.")
    if not response.ok:
        raise HTTPException(status_code=502, detail="Unable to send verification email")


def issue_otp(user: dict[str, Any], kind: str) -> None:
    code = f"{secrets.randbelow(1_000_000):06d}"
    field = "verification" if kind == "verification" else "passwordReset"
    update = {f"{field}OtpHash": otp_hash(code), f"{field}OtpExpiresAt": utcnow() + timedelta(minutes=OTP_MINUTES), f"{field}OtpAttempts": 0}
    get_database().users.update_one({"_id": user["_id"]}, {"$set": update})
    subject = "Verify your LegalLense email" if kind == "verification" else "LegalLense password reset code"
    send_email(user["email"], subject, f"<p>Your LegalLense verification code is <strong>{code}</strong>.</p><p>This code expires in {OTP_MINUTES} minutes.</p>")


def current_user(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict[str, Any]:
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    token_hash = hashlib.sha256(session.encode("utf-8")).hexdigest()
    record = get_database().sessions.find_one({"tokenHash": token_hash, "expiresAt": {"$gt": utcnow()}})
    if not record:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = get_database().users.find_one({"_id": record["userId"]})
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_role(role: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a dependency that authorizes one role from the database record."""
    def dependency(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user.get("role") != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


official_user = require_role("official")
manufacturer_user = require_role("manufacturer")


class SignupRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    companyName: str | None = None
    gstin: str | None = None


class OfficialProvisionRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: str = "manufacturer"


class OtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")


class EmailRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(OtpRequest):
    password: str = Field(min_length=8, max_length=128)


class ProfileRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)


def set_session(response: Response, user: dict[str, Any]) -> None:
    token = secrets.token_urlsafe(48)
    get_database().sessions.insert_one({"tokenHash": hashlib.sha256(token.encode()).hexdigest(), "userId": user["_id"], "createdAt": utcnow(), "expiresAt": utcnow() + timedelta(days=SESSION_DAYS)})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=False, max_age=SESSION_DAYS * 86400, path="/")


@router.post("/signup")
def signup(payload: SignupRequest):
    db = get_database()
    email = normalize_email(str(payload.email))
    existing = db.users.find_one({"email": email})
    if existing and existing.get("emailVerified"):
        raise HTTPException(status_code=409, detail="Account already exists. Please log in.")
    password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    now = utcnow()
    user_data = {"fullName": payload.fullName.strip(), "email": email, "passwordHash": password_hash, "companyName": (payload.companyName or "").strip(), "gstin": (payload.gstin or "").strip(), "emailVerified": False, "createdAt": now, "updatedAt": now}
    if existing:
        db.users.update_one({"_id": existing["_id"]}, {"$set": user_data})
        user = db.users.find_one({"_id": existing["_id"]})
    else:
        user_data["role"] = "manufacturer"
        user_data["verificationOtpAttempts"] = 0
        user_id = db.users.insert_one(user_data).inserted_id
        user = db.users.find_one({"_id": user_id})
    if user.get("companyName"):
        company = db.companies.find_one({"ownerUserId": user["_id"]})
        company_data = {"ownerUserId": user["_id"], "name": user["companyName"], "gstin": user.get("gstin", ""), "updatedAt": now}
        if company:
            db.companies.update_one({"_id": company["_id"]}, {"$set": company_data})
            company_id = company["_id"]
        else:
            company_data["createdAt"] = now
            company_id = db.companies.insert_one(company_data).inserted_id
        db.users.update_one({"_id": user["_id"]}, {"$set": {"companyId": company_id}})
    issue_otp(user, "verification")
    return {"success": True, "message": "Account created. Check your email for the verification code.", "email": email}


@router.post("/provision-official")
def provision_official(payload: OfficialProvisionRequest, x_provision_key: str | None = Header(default=None)):
    """Create or replace an official account using the server-only provision key."""
    provision_key = os.getenv("OFFICIAL_PROVISION_KEY", "").strip()
    if not provision_key or not x_provision_key or not secrets.compare_digest(x_provision_key, provision_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Official provisioning is not authorized")
    db = get_database()
    email = normalize_email(str(payload.email))
    now = utcnow()
    user_data = {"fullName": payload.fullName.strip(), "email": email, "passwordHash": bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode(), "role": "official", "companyName": "", "emailVerified": True, "updatedAt": now, "lastLoginAt": None}
    existing = db.users.find_one({"email": email})
    if existing:
        db.users.update_one({"_id": existing["_id"]}, {"$set": user_data})
        user = db.users.find_one({"_id": existing["_id"]})
    else:
        user_data["createdAt"] = now
        user_id = db.users.insert_one(user_data).inserted_id
        user = db.users.find_one({"_id": user_id})
    db.sessions.delete_many({"userId": user["_id"]})
    return {"success": True, "user": public_user(user)}


@router.post("/verify-email")
def verify_email(payload: OtpRequest):
    user = get_database().users.find_one({"email": normalize_email(str(payload.email))})
    if not user or user.get("emailVerified"):
        raise HTTPException(status_code=400, detail="Invalid verification request")
    if user.get("verificationOtpAttempts", 0) >= 5 or not user.get("verificationOtpExpiresAt") or user["verificationOtpExpiresAt"] < utcnow() or not secrets.compare_digest(user.get("verificationOtpHash", ""), otp_hash(payload.otp)):
        get_database().users.update_one({"_id": user["_id"]}, {"$inc": {"verificationOtpAttempts": 1}})
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    get_database().users.update_one({"_id": user["_id"]}, {"$set": {"emailVerified": True, "updatedAt": utcnow()}, "$unset": {"verificationOtpHash": "", "verificationOtpExpiresAt": "", "verificationOtpAttempts": ""}})
    return {"success": True, "message": "Email verified. You can now log in."}


@router.post("/resend-verification")
def resend_verification(payload: EmailRequest):
    user = get_database().users.find_one({"email": normalize_email(str(payload.email)), "emailVerified": False})
    if user:
        issue_otp(user, "verification")
    return {"success": True, "message": "If the account exists, a new verification code was sent."}


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    user = get_database().users.find_one({"email": normalize_email(str(payload.email))})
    if not user or not bcrypt.checkpw(payload.password.encode(), user["passwordHash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("emailVerified", False):
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")
    if payload.role and user.get("role") != payload.role:
        if payload.role == "official":
            raise HTTPException(status_code=403, detail="Invalid account type. Please use Manufacturer login.")
        raise HTTPException(status_code=403, detail="Invalid account type. Please use Official login.")
    get_database().users.update_one({"_id": user["_id"]}, {"$set": {"lastLoginAt": utcnow()}})
    set_session(response, user)
    return {"success": True, "user": public_user(user)}


@router.post("/logout")
def logout(response: Response, session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if session:
        get_database().sessions.delete_one({"tokenHash": hashlib.sha256(session.encode()).hexdigest()})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"success": True}


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)):
    return {"success": True, "user": public_user(user)}


@router.post("/forgot-password")
def forgot_password(payload: EmailRequest):
    user = get_database().users.find_one({"email": normalize_email(str(payload.email))})
    if user:
        issue_otp(user, "reset")
    return {"success": True, "message": "If the account exists, a password reset code was sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    user = get_database().users.find_one({"email": normalize_email(str(payload.email))})
    if not user or user.get("passwordResetOtpAttempts", 0) >= 5 or not user.get("passwordResetOtpExpiresAt") or user["passwordResetOtpExpiresAt"] < utcnow() or not secrets.compare_digest(user.get("passwordResetOtpHash", ""), otp_hash(payload.otp)):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    hashed = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    get_database().users.update_one({"_id": user["_id"]}, {"$set": {"passwordHash": hashed, "updatedAt": utcnow()}, "$unset": {"passwordResetOtpHash": "", "passwordResetOtpExpiresAt": "", "passwordResetOtpAttempts": ""}})
    get_database().sessions.delete_many({"userId": user["_id"]})
    return {"success": True, "message": "Password reset successfully."}


@router.get("/profile")
def profile(user: dict[str, Any] = Depends(current_user)):
    return {"success": True, "user": public_user(user)}


@router.put("/profile")
def update_profile(payload: ProfileRequest, user: dict[str, Any] = Depends(current_user)):
    get_database().users.update_one({"_id": user["_id"]}, {"$set": {"fullName": payload.fullName.strip(), "updatedAt": utcnow()}})
    return {"success": True, "user": public_user({**user, "fullName": payload.fullName.strip()})}


@router.get("/history")
def history(user: dict[str, Any] = Depends(current_user)):
    records = get_database().history.find({"userId": user["_id"]}, {"_id": 0}).sort("createdAt", -1)
    return {"success": True, "items": list(records)}


@router.get("/dashboard")
def dashboard(user: dict[str, Any] = Depends(current_user)):
    db = get_database()
    query = {"userId": user["_id"]}
    if user.get("role") == "official":
        scans = list(db.scans.find(query, {"_id": 0, "status": 1, "score": 1}))
        scored = [scan for scan in scans if isinstance(scan.get("score"), (int, float))]
        compliant = sum(scan.get("status") == "compliant" for scan in scored)
        return {"success": True, "role": "official", "stats": {"totalScans": len(scans), "openViolations": db.cases.count_documents({**query, "status": {"$in": ["open", "under_review", "escalated"]}}), "escalatedCases": db.cases.count_documents({**query, "status": "escalated"}), "closedCases": db.cases.count_documents({**query, "status": "closed"}), "complianceRate": round(compliant / len(scored) * 100) if scored else 0}}
    products = list(db.products.find({"manufacturerId": user["_id"]}, {"_id": 0, "productId": 1, "latestStatus": 1, "latestScore": 1}))
    compliant_products = sum(product.get("latestStatus") == "compliant" for product in products)
    scores = [product["latestScore"] for product in products if isinstance(product.get("latestScore"), (int, float))]
    return {"success": True, "role": "manufacturer", "stats": {"totalProducts": len(products), "compliantProducts": compliant_products, "needsFixes": len(products) - compliant_products, "complianceScore": round(sum(scores) / len(scores)) if scores else 0}}
