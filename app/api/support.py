from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict
from app.models.support import (
    TicketCreate, TicketUpdate, TicketPublic, TicketDetail,
    MessageCreate, TicketStats, TicketStatus, TicketCategory, TicketPriority,
    SupportOverview
)
from app.services.support_service import support_service
from app.api.auth import get_current_user
from app.models.user import UserPublic

router = APIRouter(prefix="/support", tags=["support"])

# === ENDPOINTS MÉTADONNÉES ===

@router.get("/categories", response_model=List[Dict[str, str]])
async def get_ticket_categories():
    """Récupérer toutes les catégories de tickets disponibles"""
    categories = []
    for category in TicketCategory:
        # Ajouter des descriptions conviviales
        descriptions = {
            "commande": "Problème avec une commande (livraison, contenu, etc.)",
            "produit": "Question ou problème concernant un produit",
            "paiement": "Problème de paiement ou facturation",
            "livraison": "Retard, colis perdu ou problème de livraison",
            "technique": "Problème technique avec le site ou l'application",
            "autre": "Autre sujet non couvert par les catégories ci-dessus"
        }
        
        categories.append({
            "value": category.value,
            "label": category.value.title(),
            "description": descriptions.get(category.value, "")
        })
    
    return categories

@router.get("/priorities", response_model=List[Dict[str, str]])
async def get_ticket_priorities():
    """Récupérer toutes les priorités de tickets disponibles"""
    priorities = []
    for priority in TicketPriority:
        # Ajouter des descriptions et couleurs
        descriptions = {
            "basse": "Non urgent - peut attendre quelques jours",
            "normale": "Priorité standard - traitement sous 48h",
            "haute": "Important - traitement sous 24h",
            "urgente": "Très urgent - traitement immédiat requis"
        }
        
        colors = {
            "basse": "#28a745",     # Vert
            "normale": "#007bff",   # Bleu
            "haute": "#fd7e14",     # Orange
            "urgente": "#dc3545"    # Rouge
        }
        
        priorities.append({
            "value": priority.value,
            "label": priority.value.title(),
            "description": descriptions.get(priority.value, ""),
            "color": colors.get(priority.value, "#6c757d")
        })
    
    return priorities

@router.get("/statuses", response_model=List[Dict[str, str]])
async def get_ticket_statuses():
    """Récupérer tous les statuts de tickets disponibles"""
    statuses = []
    for status in TicketStatus:
        descriptions = {
            "ouvert": "Nouveau ticket en attente de traitement",
            "en_cours": "Ticket pris en charge par un vendeur",
            "resolu": "Problème résolu, en attente de confirmation",
            "ferme": "Ticket définitivement fermé"
        }
        
        colors = {
            "ouvert": "#ffc107",     # Jaune
            "en_cours": "#007bff",   # Bleu
            "resolu": "#28a745",     # Vert
            "ferme": "#6c757d"       # Gris
        }
        
        statuses.append({
            "value": status.value,
            "label": status.value.replace("_", " ").title(),
            "description": descriptions.get(status.value, ""),
            "color": colors.get(status.value, "#6c757d")
        })
    
    return statuses

# === ENDPOINTS CLIENTS ===

@router.post("/tickets", response_model=TicketPublic)
async def create_ticket(
    ticket: TicketCreate,
    current_user: UserPublic = Depends(get_current_user)
):
    """Créer un nouveau ticket de support (client)"""
    return await support_service.create_ticket(ticket, current_user.id)

@router.get("/tickets/suggestions")
async def get_ticket_suggestions(
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupérer des suggestions pour créer un ticket basées sur l'historique du client"""
    # Récupérer les commandes récentes du client pour suggestions contextuelles
    suggestions = {
        "recent_orders": [],
        "common_issues": [
            {
                "title": "Je n'ai pas reçu ma commande",
                "category": "livraison",
                "priority": "haute",
                "template": "Je n'ai pas encore reçu ma commande passée le [DATE]. Pouvez-vous vérifier le statut de la livraison ?"
            },
            {
                "title": "Produit défectueux ou endommagé",
                "category": "produit", 
                "priority": "haute",
                "template": "Le produit que j'ai reçu est [DÉCRIRE LE PROBLÈME]. Je souhaiterais un échange ou un remboursement."
            },
            {
                "title": "Problème de paiement",
                "category": "paiement",
                "priority": "normale",
                "template": "J'ai un problème avec le paiement de ma commande [NUMÉRO]. [DÉCRIRE LE PROBLÈME]"
            },
            {
                "title": "Question sur un produit",
                "category": "produit",
                "priority": "basse", 
                "template": "J'ai une question concernant le produit [NOM DU PRODUIT]. [POSER LA QUESTION]"
            },
            {
                "title": "Retour ou échange",
                "category": "commande",
                "priority": "normale",
                "template": "Je souhaiterais retourner/échanger le produit [NOM] de ma commande [NUMÉRO] car [RAISON]."
            }
        ],
        "quick_actions": [
            {
                "label": "Suivre ma commande",
                "action": "track_order",
                "description": "Voir le statut de vos commandes en cours"
            },
            {
                "label": "Contacter le vendeur",
                "action": "contact_seller", 
                "description": "Message direct au vendeur du produit"
            }
        ]
    }
    
    return suggestions

@router.get("/tickets", response_model=List[TicketPublic])
async def get_my_tickets(
    status: Optional[TicketStatus] = Query(None),
    category: Optional[TicketCategory] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupérer mes tickets (client)"""
    if current_user.role == "client":
        return await support_service.get_tickets(
            customer_id=current_user.id,
            status=status.value if status else None,
            category=category.value if category else None,
            skip=skip,
            limit=limit
        )
    else:
        # Admin/vendeur : voir tous les tickets ou ceux assignés
        return await support_service.get_tickets(
            assigned_to=current_user.id if current_user.role == "vendeur" else None,
            status=status.value if status else None,
            category=category.value if category else None,
            skip=skip,
            limit=limit
        )

@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: str,
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupérer un ticket avec ses messages"""
    ticket = await support_service.get_ticket(ticket_id, with_messages=True)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket non trouvé")
    
    # Vérifier les permissions
    if (current_user.role == "client" and ticket.customer_id != current_user.id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    return ticket

@router.post("/tickets/{ticket_id}/messages", response_model=TicketDetail)
async def add_message(
    ticket_id: str,
    message: MessageCreate,
    current_user: UserPublic = Depends(get_current_user)
):
    """Ajouter un message à un ticket"""
    # Vérifier que le ticket existe et que l'utilisateur a accès
    ticket = await support_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket non trouvé")
    
    if (current_user.role == "client" and ticket.customer_id != current_user.id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    result = await support_service.add_message(ticket_id, message, current_user.id)
    if not result:
        raise HTTPException(status_code=400, detail="Impossible d'ajouter le message")
    
    return result

# === ENDPOINTS VENDEURS ===

@router.get("/vendor/tickets", response_model=List[TicketPublic])
async def get_vendor_tickets(
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupérer les tickets du vendeur (assignés + non assignés)"""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux vendeurs")
    
    return await support_service.get_vendor_tickets(current_user.id)

@router.put("/vendor/tickets/{ticket_id}/assign", response_model=TicketPublic)
async def assign_ticket_to_me(
    ticket_id: str,
    current_user: UserPublic = Depends(get_current_user)
):
    """S'assigner un ticket (vendeur/admin)"""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux vendeurs")
    
    result = await support_service.assign_ticket(ticket_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Ticket non trouvé")
    
    return result

@router.put("/vendor/tickets/{ticket_id}/status", response_model=TicketPublic)
async def update_ticket_status(
    ticket_id: str,
    status: TicketStatus,
    priority: Optional[TicketPriority] = Query(None),
    current_user: UserPublic = Depends(get_current_user)
):
    """Mettre à jour le statut d'un ticket (vendeur/admin)"""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux vendeurs")
    
    update_data = TicketUpdate(status=status)
    if priority:
        update_data.priority = priority
    
    result = await support_service.update_ticket(ticket_id, update_data, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Ticket non trouvé")
    
    return result

# === ENDPOINTS ADMIN ===

@router.get("/admin/tickets", response_model=List[TicketPublic])
async def get_all_tickets(
    status: Optional[TicketStatus] = Query(None),
    category: Optional[TicketCategory] = Query(None),
    assigned_to: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupérer tous les tickets (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    return await support_service.get_tickets(
        assigned_to=assigned_to,
        status=status.value if status else None,
        category=category.value if category else None,
        skip=skip,
        limit=limit
    )

@router.put("/admin/tickets/{ticket_id}", response_model=TicketPublic)
async def update_ticket(
    ticket_id: str,
    update: TicketUpdate,
    current_user: UserPublic = Depends(get_current_user)
):
    """Mettre à jour un ticket (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    result = await support_service.update_ticket(ticket_id, update, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Ticket non trouvé")
    
    return result

@router.get("/admin/stats", response_model=TicketStats)
async def get_support_stats(
    current_user: UserPublic = Depends(get_current_user)
):
    """Statistiques de support (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    return await support_service.get_support_stats()

@router.get("/vendor/stats", response_model=TicketStats)
async def get_vendor_support_stats(
    current_user: UserPublic = Depends(get_current_user)
):
    """Statistiques de support pour vendeur"""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux vendeurs")
    
    return await support_service.get_support_stats(current_user.id)

@router.get("/overview", response_model=Dict)
async def get_support_overview(
    current_user: UserPublic = Depends(get_current_user)
):
    """Résumé des tickets de support avec comptes par statut (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    return await support_service.get_support_overview()
