"""Request bodies (Pydantic v2). Responses are plain dicts built in the service layer."""
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

CITIES = ["Chennai", "Coimbatore", "Madurai", "Bengaluru", "Hyderabad", "Mumbai", "Delhi"]
WORK_TYPES = ["rider", "home_service", "freelancer", "vendor"]
LANGS = ["en", "ta", "hi"]
SOURCE_KINDS = ["bank_statement", "platform_statement", "account_aggregator"]
CONSENT_PURPOSES = ["income_assessment", "loan_application", "monitoring"]
DECISION_REASON_CODES = {
    "approve": ["CAPACITY_SUFFICIENT", "CONSISTENT_EARNINGS", "VERIFIED_MULTI_SOURCE", "OFFICER_JUDGEMENT"],
    "modify": ["REDUCE_EMI_TO_SAFE_LEVEL", "SHORTER_TENURE", "ADD_SKIP_WEEK", "LOWER_AMOUNT", "OFFICER_JUDGEMENT"],
    "decline": ["INSUFFICIENT_CAPACITY", "UNVERIFIED_INCOME", "ANTI_GAMING_FLAG_CONFIRMED", "INSUFFICIENT_DATA",
                "EXISTING_DEBT_TOO_HIGH", "OFFICER_JUDGEMENT"],
}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str = Field(min_length=2, max_length=120)
    city: Literal["Chennai", "Coimbatore", "Madurai", "Bengaluru", "Hyderabad", "Mumbai", "Delhi"]
    work_type: Literal["rider", "home_service", "freelancer", "vendor"]
    languages: list[Literal["en", "ta", "hi"]] = ["en"]
    preferred_language: Literal["en", "ta", "hi"] = "en"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    city: Literal["Chennai", "Coimbatore", "Madurai", "Bengaluru", "Hyderabad", "Mumbai", "Delhi"]
    work_type: Literal["rider", "home_service", "freelancer", "vendor"]
    languages: list[Literal["en", "ta", "hi"]]
    preferred_language: Literal["en", "ta", "hi"]
    group_attr: Literal["woman", "man", "non_binary"] | None = None
    group_attr_consent: bool = False
    training_consent: bool = False


class ConsentIn(BaseModel):
    source_kind: Literal["bank_statement", "platform_statement", "account_aggregator"]
    purpose: Literal["income_assessment", "loan_application", "monitoring"]
    days: int = Field(default=90, ge=1, le=365)


class MappingIn(BaseModel):
    date: str
    narration: str
    debit: str | None = None
    credit: str | None = None
    amount: str | None = None
    balance: str | None = None
    ref: str | None = None
    date_format: Literal["auto", "dd/mm/yyyy", "dd-mm-yy", "yyyy-mm-dd", "mm/dd/yyyy"] = "auto"

    @field_validator("date", "narration")
    @classmethod
    def required(cls, v: str) -> str:
        if not v:
            raise ValueError("required")
        return v


class CategoryIn(BaseModel):
    category: Literal["rent", "utilities", "fuel", "emi", "savings", "other"]


class ShareIn(BaseModel):
    lender_id: int
    days: int = Field(default=14, ge=1, le=90)
    requested_amount: float = Field(gt=0, le=1_000_000)
    requested_tenure_weeks: int = Field(ge=4, le=156)
    purpose: str = Field(default="", max_length=120)


class DisputeIn(BaseModel):
    category: Literal["score", "decision", "data"]
    description: str = Field(min_length=10, max_length=2000)
    application_id: int | None = None
    snapshot_id: int | None = None


class DisputeUpdateIn(BaseModel):
    status: Literal["open", "in_review", "resolved"]
    response: str = Field(default="", max_length=2000)


class DecisionIn(BaseModel):
    outcome: Literal["approve", "modify", "decline"]
    reason_code: str
    note: str = Field(min_length=5, max_length=2000)
    weekly_emi: float | None = Field(default=None, ge=0)
    tenure_weeks: int | None = Field(default=None, ge=4, le=156)
    amount: float | None = Field(default=None, ge=0)
    skip_weeks: list[str] = []


class LenderIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    alpha: float = Field(default=0.5, gt=0, le=1)
    annual_rate: float = Field(default=0.24, ge=0, le=0.6)
    default_tenure_weeks: int = Field(default=52, ge=4, le=156)
    grievance_email: EmailStr | None = None


class UserAdminIn(BaseModel):
    is_active: bool | None = None
    role: Literal["worker", "officer", "admin"] | None = None
    lender_id: int | None = None


class StaffIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str
    role: Literal["officer", "admin"]
    lender_id: int | None = None
