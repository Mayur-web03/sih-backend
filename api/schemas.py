import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator


class TraceRequest(BaseModel):
    address: str
    max_hops: int = 5
    case_id: Optional[str] = None  # if provided, persisted transactions are linked to this case

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^0x[a-fA-F0-9]{40}$", v):
            raise ValueError("Invalid Ethereum address format")
        return v.lower()

    @field_validator("max_hops")
    @classmethod
    def validate_max_hops(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_hops must be between 1 and 10")
        return v


# ============================================================
# TRON TRACE REQUEST SCHEMA
# ============================================================

class TronTraceRequest(BaseModel):
    address: str
    max_hops: int = 3
    asset_type: str = "all"
    case_id: Optional[str] = None

    @field_validator("address")
    @classmethod
    def validate_tron_address(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^T[1-9A-HJ-NP-Za-km-z]{33}$", v):
            raise ValueError("Invalid TRON address format")
        return v

    @field_validator("max_hops")
    @classmethod
    def validate_tron_max_hops(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_hops must be between 1 and 10")
        return v

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"trx", "trc20", "all"}:
            raise ValueError("asset_type must be trx, trc20, or all")
        return v


class TransactionRecord(BaseModel):
    hop: int
    direction: str
    from_: str
    to: str
    value: str
    tx_hash: str
    block_number: str
    timestamp: str
    gas_used: str
    gas_price: str
    is_error: str
    source_address: str

    class Config:
        populate_by_name = True


class TraceSummary(BaseModel):
    inward_transactions: int
    outward_transactions: int
    total_transactions: int
    max_hops: int


class TraceResponse(BaseModel):
    address: str
    summary: TraceSummary
    inward: List[dict]
    outward: List[dict]


# ============================================================
# CASES
# ============================================================

class CaseCreate(BaseModel):
    id: Optional[str] = None            # e.g. NCRP-2026-xxxx; auto-generated if omitted
    complaint_id: Optional[str] = None
    victim_name: Optional[str] = None
    primary_wallet: str
    amount_inr: Optional[float] = None
    chain: str = "Ethereum"
    fraud_type: Optional[str] = None
    status: str = "New"
    priority: str = "Medium"
    assigned_investigator: Optional[str] = None
    auto_trace: bool = True
    max_hops: int = 5

    @model_validator(mode="after")
    def validate_wallet_for_chain(self):
        wallet = self.primary_wallet.strip()
        chain = self.chain.strip().lower()

        if chain == "tron":
            if not re.match(r"^T[1-9A-HJ-NP-Za-km-z]{33}$", wallet):
                raise ValueError("Invalid TRON address format")
            self.primary_wallet = wallet
        else:
            if not re.match(r"^0x[a-fA-F0-9]{40}$", wallet):
                raise ValueError("Invalid Ethereum address format")
            self.primary_wallet = wallet.lower()

        return self


class CaseUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_investigator: Optional[str] = None
    risk_score: Optional[int] = None
    fraud_type: Optional[str] = None
    victim_name: Optional[str] = None
    amount_inr: Optional[float] = None


class CaseOut(BaseModel):
    id: str
    complaint_id: Optional[str] = None
    victim_name: Optional[str] = None
    primary_wallet: str
    amount_inr: Optional[float] = None
    chain: Optional[str] = None
    fraud_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    risk_score: Optional[int] = None
    assigned_investigator: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
