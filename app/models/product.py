# === CORRECTIONS POUR PRODUCT.PY (MODÈLES) ===

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class ProductSize(str, Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    XXL = "XXL"

class ProductCategory(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    parent_id: Optional[str] = None

class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    cost_price: float = Field(0, ge=0, description="Prix de revient unitaire (coût)")
    currency: str = Field("XOF", min_length=1, max_length=5, description="Devise du prix")
    category_id: str = Field(..., min_length=1)
    sizes: List[ProductSize] = Field(default_factory=list)
    colors: List[str] = Field(default_factory=list)
    stock: int = Field(..., ge=0)
    reserved_stock: int = Field(0, ge=0, description="Quantité de stock réservée pour commandes en versements")
    low_stock_threshold: int = Field(0, ge=0, description="Seuil d'alerte stock bas")
    images: List[str] = Field(default_factory=list)
    hover_images: List[str] = Field(default_factory=list, description="Images affichées au survol")
    tags: List[str] = Field(default_factory=list)

class ProductCreate(ProductBase):
    """Modèle pour créer un produit."""
    pass

class ProductUpdate(BaseModel):
    """Modèle pour mettre à jour un produit."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    price: Optional[float] = Field(None, gt=0)
    cost_price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field("XOF", min_length=1, max_length=5)
    category_id: Optional[str] = Field(None, min_length=1)
    sizes: Optional[List[ProductSize]] = None
    colors: Optional[List[str]] = None
    stock: Optional[int] = Field(None, ge=0)
    low_stock_threshold: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = Field(None, description="Activer ou désactiver le produit")
    images: Optional[List[str]] = None
    hover_images: Optional[List[str]] = Field(None, description="Images affichées au survol")
    tags: Optional[List[str]] = None

class ProductInDB(ProductBase):
    """Modèle pour un produit en base de données."""
    id: str
    seller_id: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

class ProductPublic(ProductBase):
    """Modèle pour un produit public (API)."""
    id: str
    seller_id: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    category: Optional[ProductCategory] = None
    profit: float = 0
    margin_percent: float = 0
    discounted_price: Optional[float] = None  # Prix réduit si promotion active
    discount_amount: Optional[float] = None  # Montant de la réduction

    @model_validator(mode='after')
    def compute_profit_margin(self):
        """Calcule le profit et la marge."""
        try:
            price = float(self.price or 0)
            cost = float(self.cost_price or 0)
            profit = price - cost
            margin_percent = (profit / price * 100) if price > 0 else 0
            self.profit = round(profit, 2)
            self.margin_percent = round(margin_percent, 2)
        except (ValueError, TypeError):
            self.profit = 0
            self.margin_percent = 0
        return self

    class Config:
        """Configuration Pydantic."""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# === MODÈLES CATÉGORIES ===

class CategoryBase(BaseModel):
    """Modèle de base pour les catégories."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[str] = None

class CategoryCreate(CategoryBase):
    """Modèle pour créer une catégorie."""
    pass

class CategoryUpdate(BaseModel):
    """Modèle pour mettre à jour une catégorie."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[str] = None

class CategoryInDB(CategoryBase):
    """Modèle pour une catégorie en base de données."""
    id: str
    created_at: datetime
    updated_at: datetime

class CategoryPublic(CategoryBase):
    """Modèle pour une catégorie publique (API)."""
    id: str
    created_at: datetime
    updated_at: datetime
    children: List['CategoryPublic'] = Field(default_factory=list)

    class Config:
        """Configuration Pydantic."""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Pour la récursion des catégories              
CategoryPublic.model_rebuild()

# === MODÈLES DE RÉPONSE ===

class ProductListResponse(BaseModel):
    """Réponse pour une liste de produits."""
    products: List[ProductPublic]
    total: int
    page: int
    size: int
    has_next: bool

class CategoryListResponse(BaseModel):
    """Réponse pour une liste de catégories."""
    categories: List[CategoryPublic]
    total: int

# === MODÈLES DE FILTRE ===

class ProductFilters(BaseModel):
    """Filtres pour rechercher des produits."""
    category_id: Optional[str] = None
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    sizes: Optional[List[str]] = None
    colors: Optional[List[str]] = None
    search: Optional[str] = None
    name: Optional[str] = None
    seller_id: Optional[str] = None
    is_active: Optional[bool] = True
    in_stock: Optional[bool] = None  # Produits en stock uniquement

class ProductStats(BaseModel):
    """Statistiques des produits."""
    total_products: int
    active_products: int
    inactive_products: int
    low_stock_products: int
    out_of_stock_products: int
    total_value: float
    categories_count: int