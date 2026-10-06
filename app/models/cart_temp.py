from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class CartItem(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    size: Optional[str] = None
    color: Optional[str] = None
    images: Optional[List[str]] = None  # URLs des images du produit
    original_price: Optional[float] = None  # prix original du produit
    price: Optional[float] = None  # prix unitaire du produit (réduit si promotion)
    discounted_price: Optional[float] = None  # prix réduit explicite
    name: Optional[str] = None     # nom du produit
    discount_amount: Optional[float] = None  # montant de la réduction appliquée
    # On peut ajouter d'autres options (ex: customisation)

class CartBase(BaseModel):
    items: List[CartItem] = []

class CartCreate(CartBase):
    pass

class CartUpdate(CartBase):
    pass

class CartInDB(CartBase):
    id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class CartPublic(CartBase):
    id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    total: float = 0.0

# Nouveaux modèles pour les requêtes d'update
class UpdateQuantityRequest(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    size: Optional[str] = None
    color: Optional[str] = None

class QuantityChangeRequest(BaseModel):
    product_id: str
    size: Optional[str] = None
    color: Optional[str] = None

class BatchUpdateAction(BaseModel):
    action: str  # "increase" ou "decrease"
    product_id: str
    size: Optional[str] = None
    color: Optional[str] = None

class BatchUpdateRequest(BaseModel):
    actions: List[BatchUpdateAction]
