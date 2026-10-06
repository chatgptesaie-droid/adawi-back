from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class Notification(BaseModel):
    id: Optional[str]
    user_id: str  # "admin", id du vendeur, etc.
    type: str     # "nouvelle_commande", "paiement", "low_stock", "new_ticket", "refund_requested", etc.
    message: str
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    ticket_id: Optional[str] = None
    refund_id: Optional[str] = None
    order_details: Optional[Dict[str, Any]] = None  # Détails enrichis pour les notifications de commande
    product_details: Optional[Dict[str, Any]] = None  # Détails enrichis pour les notifications de produit
    ticket_details: Optional[Dict[str, Any]] = None  # Détails enrichis pour les notifications de ticket
    refund_details: Optional[Dict[str, Any]] = None  # Détails enrichis pour les notifications de remboursement
    created_at: datetime
    read: bool = False
 