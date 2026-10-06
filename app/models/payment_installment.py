from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from enum import Enum

class PaymentMethod(str, Enum):
    CASH = "cash"
    

class InstallmentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"

class PaymentInstallment(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id", validation_alias="_id")
    order_id: str = Field(..., description="ID de la commande associée")
    installment_number: int = Field(..., description="Numéro du versement (1, 2, 3...)")
    amount: float = Field(..., description="Montant dû pour ce versement")
    paid_amount: float = Field(default=0.0, description="Montant réellement payé")
    due_date: datetime = Field(..., description="Date d'échéance du versement")
    status: InstallmentStatus = Field(default=InstallmentStatus.PENDING, description="Statut du versement")
    payment_method: Optional[PaymentMethod] = Field(default=None, description="Méthode de paiement utilisée")
    paid_at: Optional[datetime] = Field(default=None, description="Date de paiement effectif")
    notes: Optional[str] = Field(default=None, description="Notes sur le paiement")
    created_by: str = Field(..., description="ID du vendeur/admin qui a créé le versement")
    paid_by: Optional[str] = Field(default=None, description="ID du vendeur/admin qui a encaissé")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }
    }

class PaymentInstallmentCreate(BaseModel):
    order_id: str
    installment_number: int
    amount: float
    due_date: datetime
    notes: Optional[str] = None

class PaymentInstallmentUpdate(BaseModel):
    paid_amount: Optional[float] = None
    payment_method: Optional[PaymentMethod] = None
    status: Optional[InstallmentStatus] = None
    notes: Optional[str] = None
    paid_by: Optional[str] = None

class PaymentInstallmentPublic(PaymentInstallment):
    pass

class InstallmentPlanCreate(BaseModel):
    installments_count: int = Field(..., ge=2, le=12, description="Nombre de versements (2-12)")
    first_payment_amount: float = Field(..., gt=0, description="Montant du premier versement")
    installment_amount: float = Field(..., gt=0, description="Montant des versements suivants")
    due_dates: List[datetime] = Field(..., description="Dates d'échéance pour chaque versement")
    customer_name: str = Field(..., description="Nom du client pour les commandes en versements")
    customer_phone: str = Field(..., description="Numéro de téléphone du client")
    user_email: Optional[str] = Field(default=None, description="Email de l'utilisateur existant pour lier la commande")
    notes: Optional[str] = Field(default=None, description="Notes générales sur le plan de paiement")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
