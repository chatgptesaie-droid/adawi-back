from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class TicketStatus(str, Enum):
    ouvert = "ouvert"
    en_cours = "en_cours"
    resolu = "resolu"
    ferme = "ferme"

class TicketPriority(str, Enum):
    basse = "basse"
    normale = "normale"
    haute = "haute"
    urgente = "urgente"

class TicketCategory(str, Enum):
    commande = "commande"
    produit = "produit"
    paiement = "paiement"
    livraison = "livraison"
    technique = "technique"
    autre = "autre"

class TicketMessage(BaseModel):
    id: str
    ticket_id: str
    author_id: str
    author_name: str
    author_role: str  # client, vendeur, admin
    message: str
    created_at: datetime
    is_internal: bool = False  # Message interne entre staff

class TicketBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10)
    category: TicketCategory
    priority: TicketPriority = TicketPriority.normale
    order_id: Optional[str] = None  # Lié à une commande spécifique

class TicketCreate(TicketBase):
    pass

class TicketUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    category: Optional[TicketCategory] = None
    priority: Optional[TicketPriority] = None
    status: Optional[TicketStatus] = None
    assigned_to: Optional[str] = None  # ID du vendeur/admin assigné

class TicketInDB(TicketBase):
    id: str
    customer_id: str
    status: TicketStatus = TicketStatus.ouvert
    assigned_to: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    messages: List[TicketMessage] = []

class TicketPublic(TicketBase):
    id: str
    customer_id: str
    customer_name: Optional[str] = None
    status: TicketStatus
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    messages_count: int = 0
    last_message_at: Optional[datetime] = None

class TicketDetail(TicketPublic):
    messages: List[TicketMessage] = []

class MessageCreate(BaseModel):
    message: str = Field(..., min_length=1)
    is_internal: bool = False

class TicketStats(BaseModel):
    total_tickets: int
    open_tickets: int
    in_progress_tickets: int
    resolved_tickets: int
    closed_tickets: int
    average_resolution_time: float  # en heures
    tickets_by_category: List[dict]
    tickets_by_priority: List[dict]

class TicketTemplate(BaseModel):
    title: str
    category: TicketCategory
    priority: TicketPriority
    template: str
    description: Optional[str] = None

class TicketSuggestion(BaseModel):
    recent_orders: List[dict] = []
    common_issues: List[TicketTemplate] = []
    quick_actions: List[dict] = []

class SupportOverview(BaseModel):
    """Résumé complet du support pour les administrateurs"""
    # Compteurs principaux
    total_tickets: int
    tickets_by_status: dict  # {"ouvert": 5, "en_cours": 3, ...}
    tickets_by_priority: dict  # {"haute": 2, "urgente": 1, ...}
    tickets_by_category: dict  # {"commande": 4, "produit": 3, ...}
    
    # Métriques temporelles
    today_new_tickets: int
    week_new_tickets: int
    month_new_tickets: int
    
    # Performance
    average_resolution_time_hours: float
    pending_response_tickets: int  # Tickets en attente de réponse du support
    overdue_tickets: int  # Tickets en retard (>24h sans réponse)
    
    # Répartition du travail
    unassigned_tickets: int
    tickets_by_assignee: List[dict]  # [{"name": "John", "count": 5}, ...]
    
    # Tendances récentes
    resolution_rate_7days: float  # % de tickets résolus sur 7 jours
    customer_satisfaction: Optional[float] = None  # À implémenter plus tard
