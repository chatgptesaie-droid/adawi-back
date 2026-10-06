from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date
from enum import Enum
from app.models.product import ProductSize

class OrderStatus(str, Enum):
    en_cours = "en_cours"
    en_preparation = "en_preparation"
    boutique = "boutique"
    expediee = "expediee"
    livree = "livree"
    annulee = "annulee"

class PaymentStatus(str, Enum):
    en_attente = "en_attente"
    effectue = "effectue"
    refuse = "refuse"
    en_cours = "en_cours"  # Pour paiements en versements

class PaymentType(str, Enum):
    FULL = "full"  # Paiement complet
    INSTALLMENTS = "installments"  # Paiement en versements

class StatusLog(BaseModel):
    status: OrderStatus
    changed_at: datetime
    comment: Optional[str] = None

class OrderItem(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    size: Optional[str] = None
    color: Optional[str] = None
    price: float
    name: str
    images: List[str] = []

class Address(BaseModel):
    street: str
    city: str
    postal_code: str
    country: str
    phone: Optional[str] = None

class Measurements(BaseModel):
    # Mesures de base
    height: Optional[float] = None  # Taille en cm
    weight: Optional[float] = None  # Poids en kg

    # Mesures détaillées
    shoulder_width: Optional[float] = None  # Épaules en cm
    chest: Optional[float] = None  # Poitrine en cm
    waist_length: Optional[float] = None  # Longueur taille en cm
    ventral_circumference: Optional[float] = None  # Tour ventrale en cm
    hips: Optional[float] = None  # Hanche en cm
    corsage_length: Optional[float] = None  # Longueur corsage en cm
    belt: Optional[float] = None  # Ceinture en cm
    skirt_length: Optional[float] = None  # Longueur jupe en cm
    dress_length: Optional[float] = None  # Longueur robe en cm
    sleeve_length: Optional[float] = None  # Longueur manche en cm
    sleeve_circumference: Optional[float] = None  # Taille manche en cm
    pants_length: Optional[float] = None  # Longueur pantalon en cm
    short_dress_length: Optional[float] = None  # Longueur robe courte en cm
    thigh_circumference: Optional[float] = None  # Tour de cuisse en cm
    knee_length: Optional[float] = None  # Longueur de genoux en cm
    knee_circumference: Optional[float] = None  # Tour de genoux en cm
    bottom: Optional[float] = None  # Bas en cm
    inseam: Optional[float] = None  # Longueur entrejambe en cm

    # Autres mesures
    other_measurements: Optional[str] = None  # Autres mesures

class OrderBase(BaseModel):
    items: List[OrderItem]
    address: Optional[Address] = None
    total: float
    status: OrderStatus = OrderStatus.en_cours
    payment_status: PaymentStatus = PaymentStatus.en_attente
    status_history: List[StatusLog] = []
    payment_method: Optional[str] = None
    delivery_method: Optional[str] = None
    delivery_status: Optional[str] = None
    # Champs pour paiements en versements
    payment_type: PaymentType = PaymentType.FULL
    installments_count: Optional[int] = None
    paid_amount: float = 0.0
    remaining_amount: float = 0.0
    installments: List[str] = []  # Liste des IDs des versements
    # Informations client pour commandes en versements (gérées physiquement par vendeurs)
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    # Champs pour commandes sur mesure
    description: Optional[str] = None
    measurements: Optional[Measurements] = None
    photo_urls: List[str] = []
    current_size: Optional[ProductSize] = None
    delivery_type: Optional[str] = None
    delivery_date: Optional[date] = None

class CustomOrderCreate(OrderBase):
    items: List[OrderItem]
    description: str  # Description du vêtement souhaité
    measurements: Measurements
    photo_urls: List[str] = []  # URLs des photos uploadées
    current_size: ProductSize  # Taille actuelle portée
    delivery_type: str = Field(..., pattern="^(pickup|delivery)$")  # "pickup" ou "delivery"
    delivery_date: date
    address: Optional[Address] = None  # Adresse seulement si delivery
    total: float

class OrderCreate(OrderBase):
    pass

class OrderInDB(OrderBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

class OrderPublic(OrderBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime 

class OrderTrackingStep(BaseModel):
    status: OrderStatus
    label: str
    reached: bool
    date: Optional[datetime] = None

class OrderTrackingResponse(BaseModel):
    order_id: str
    current_status: OrderStatus
    steps: List[OrderTrackingStep]
    history: List[StatusLog] 