from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RefundStatus(str, Enum):
    pending = "pending"        # demande créée, en attente de review admin
    approved = "approved"      # approuvée, en attente de traitement
    rejected = "rejected"      # refusée
    processed = "processed"    # remboursée (terminée)

class RefundReason(str, Enum):
    damaged = "damaged"
    not_as_described = "not_as_described"
    wrong_item = "wrong_item"
    other = "other"

class RefundItem(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)  # prix de vente

class RefundBase(BaseModel):
    order_id: str
    reason: RefundReason = RefundReason.other
    comment: Optional[str] = None
    items: List[RefundItem] = []  # si vide => remboursement total

class RefundCreate(RefundBase):
    @validator('reason', pre=True)
    def validate_reason(cls, v):
        try:
            return RefundReason(v)
        except ValueError:
            return RefundReason.other

    @validator('items', pre=True)
    def validate_items(cls, v):
        if not isinstance(v, list):
            return []
        return v

    @validator('comment', pre=True)
    def validate_comment(cls, v):
        if not isinstance(v, str):
            return None
        return v

class RefundUpdate(BaseModel):
    status: RefundStatus
    admin_comment: Optional[str] = None

class RefundInDB(RefundBase):
    id: str
    user_id: str
    amount: float
    status: RefundStatus
    created_at: datetime
    updated_at: datetime
    admin_comment: Optional[str] = None

class RefundPublic(RefundBase):
    id: str
    user_id: str
    amount: float
    status: RefundStatus
    created_at: datetime
    updated_at: datetime
    admin_comment: Optional[str] = None

class RefundStats(BaseModel):
    total_refunds: int = 0
    total_refunded_amount: float = 0.0
    pending_refunds: int = 0
    approved_refunds: int = 0
    rejected_refunds: int = 0
    processed_refunds: int = 0
    # Champs supplémentaires potentiels ignorés dans le dashboard
    average_refund_amount: Optional[float] = None
    refunds_by_reason: Optional[List[dict]] = None
    disputes_open: Optional[int] = None
    disputes_total: Optional[int] = None
