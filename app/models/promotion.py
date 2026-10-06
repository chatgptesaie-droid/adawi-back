from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class PromotionStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"

class PromotionBase(BaseModel):
    """Modèle de base pour les promotions."""
    name: str = Field(..., min_length=1, max_length=100, description="Nom de la promotion")
    description: Optional[str] = Field(None, description="Description de la promotion")
    discount_percentage: float = Field(..., ge=0, le=100, description="Pourcentage de réduction (0-100)")
    start_date: datetime = Field(..., description="Date de début de la promotion")
    end_date: datetime = Field(..., description="Date de fin de la promotion")

class PromotionCreate(PromotionBase):
    """Modèle pour créer une promotion."""
    pass

class PromotionUpdate(BaseModel):
    """Modèle pour mettre à jour une promotion."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    discount_percentage: Optional[float] = Field(None, ge=0, le=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None

class PromotionInDB(PromotionBase):
    """Modèle pour une promotion en base de données."""
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

class PromotionPublic(PromotionBase):
    """Modèle pour une promotion publique (API)."""
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    status: PromotionStatus

    class Config:
        """Configuration Pydantic."""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# === MODÈLES DE RÉPONSE ===

class PromotionListResponse(BaseModel):
    """Réponse pour une liste de promotions."""
    promotions: list[PromotionPublic]
    total: int
    page: int
    size: int
    has_next: bool
