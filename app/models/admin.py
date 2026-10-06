from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class AdminSettings(BaseModel):
    commission_rate: float = Field(0.1, ge=0, le=1, description="Taux de commission plateforme (0-1)")
    delivery_flat_fee: float = Field(5.0, ge=0)
    delivery_per_km: float = Field(0.5, ge=0)
    free_delivery_threshold: float = Field(100.0, ge=0)
    updated_at: datetime

class AdminSettingsUpdate(BaseModel):
    commission_rate: Optional[float] = Field(None, ge=0, le=1)
    delivery_flat_fee: Optional[float] = Field(None, ge=0)
    delivery_per_km: Optional[float] = Field(None, ge=0)
    free_delivery_threshold: Optional[float] = Field(None, ge=0)

class UserAdminUpdateRole(BaseModel):
    role: str

class UserAdminBan(BaseModel):
    ban: bool

class UserAdminListResponse(BaseModel):
    users: List[dict]
    total: int

class AdminUserCreate(BaseModel):
    name: str
    email: str
    role: str = "client"
    password: str
    status: str = "Actif"  # "Actif" or "Inactif"
