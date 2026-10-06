from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId

class FactureBase(BaseModel): # La BASE (ce qui est commun à TOUTES les factures)
    phone_number: str
    amount: int
    network: str
    order_id: Optional[str] = None  # Lien vers la commande
    payment_provider: Optional[str] = "paygate"  # paygate ou moneyfusion

    class Config:
        from_attributes = True

class FactureCreate(FactureBase): # Pour créer une facture
    pass

class FactureUpdate(BaseModel): # Pour mettre à jour une facture
    status: Optional[str] = None
    payment_reference: Optional[str] = None
    amount: Optional[int] = None
    phone_number: Optional[str] = None
    network: Optional[str] = None

class FactureInDB(FactureBase): # Dans la base de données
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class FacturePublic(FactureBase): # Quand on renvoie la facture à l'utilisateur
    id: str
    created_at: datetime
    updated_at: datetime
    user_name: Optional[str] = None

    # Modèle MongoDB pour la collection factures
facture_collection = "factures"
