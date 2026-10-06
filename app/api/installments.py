from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from app.db.mongo import db
from app.models.payment_installment import (
    PaymentInstallmentPublic,
    InstallmentPlanCreate,
    PaymentMethod,
    InstallmentStatus
)
from app.models.order import OrderPublic, PaymentType
from app.services.payment_installment_service import payment_installment_service
from app.services.order_service import order_service
from app.services.cart_service import cart_service
from app.services.user_service import user_service
from app.core.auth import get_current_user
from app.models.user import UserInDB
import logging

logger = logging.getLogger(__name__)

async def _adjust_installment_plan_for_total(
    original_plan: InstallmentPlanCreate,
    actual_total: float
) -> InstallmentPlanCreate:
    """
    Ajuste le plan de versements pour correspondre au total réel du panier
    Garde le premier paiement fixe et ajuste seulement les versements suivants
    """
    from math import floor

    # Garder le premier paiement tel quel (comme demandé par l'utilisateur)
    first_payment = original_plan.first_payment_amount

    # Calculer le montant restant à répartir sur les versements suivants
    remaining_total = actual_total - first_payment
    remaining_installments = original_plan.installments_count - 1

    if remaining_installments <= 0:
        raise ValueError("Le nombre de versements doit être supérieur à 1")

    # Calculer le montant de chaque versement suivant en centimes pour éviter les erreurs d'arrondi
    remaining_total_cents = int(round(remaining_total * 100))
    base_installment_cents = remaining_total_cents // remaining_installments
    remainder_cents = remaining_total_cents % remaining_installments

    # Convertir en montant en FCFA
    base_installment_amount = base_installment_cents / 100.0

    # Le dernier versement inclura le reste des centimes
    # On ne peut pas modifier la structure InstallmentPlanCreate pour avoir un montant différent pour le dernier versement
    # Donc on garde le montant de base pour tous les versements sauf qu'on devra gérer le dernier versement différemment lors de la création des versements

    # Créer un nouveau plan ajusté avec le montant de base
    adjusted_plan = InstallmentPlanCreate(
        installments_count=original_plan.installments_count,
        first_payment_amount=round(first_payment, 2),
        installment_amount=round(base_installment_amount, 2),
        due_dates=original_plan.due_dates,
        customer_name=original_plan.customer_name,
        customer_phone=original_plan.customer_phone,
        notes=original_plan.notes
    )

    # Ajouter un attribut temporaire pour le reste à ajouter au dernier versement
    adjusted_plan._last_installment_extra = round(remainder_cents / 100.0, 2)

    return adjusted_plan

router = APIRouter(
    prefix="/installments",
    tags=["installments"],
    responses={404: {"description": "Not found"}},
)

# === ROUTES POUR LES VERSEMENTS ===

# Specific routes must come before generic ones to avoid path conflicts

@router.get("/stats")
async def get_installment_stats(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Statistiques des versements (admin/vendeur seulement)
    """
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    stats = await payment_installment_service.get_installment_stats()
    return stats

@router.get("/overdue")
async def get_overdue_installments(
    days_overdue: int = 0,
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Récupère les versements en retard (admin/vendeur seulement)
    """
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    installments = await payment_installment_service.get_overdue_installments(days_overdue)
    return {"installments": [inst.model_dump() for inst in installments], "count": len(installments)}

@router.get("/date-range")
async def get_installments_by_date_range(
    start_date: datetime = Query(..., description="Date de début"),
    end_date: datetime = Query(..., description="Date de fin"),
    status: Optional[InstallmentStatus] = None,
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Récupère les versements dans une plage de dates (admin/vendeur seulement)
    """
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    installments = await payment_installment_service.get_installments_by_date_range(
        start_date, end_date, status
    )
    return {"installments": [inst.model_dump() for inst in installments], "count": len(installments)}

@router.get("/search")
async def search_installments_by_phone(
    phone: str = Query(..., min_length=3, description="Numéro de téléphone ou partie du numéro"),
    status: Optional[InstallmentStatus] = None,
    current_user: UserInDB = Depends(get_current_user)
):
    """Recherche les versements par téléphone du client (admin/vendeur seulement)."""
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    installments = await payment_installment_service.search_installments_by_phone(phone, status)
    return {"installments": installments, "count": len(installments)}

@router.post("/update-overdue-status")
async def update_overdue_status(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Met à jour le statut des versements en retard (admin/vendeur seulement)
    """
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    updated_count = await payment_installment_service.update_overdue_status()
    return {"message": f"{updated_count} versements marqués comme en retard"}

@router.get("/order/{order_id}", response_model=List[PaymentInstallmentPublic])
async def get_installments_by_order(
    order_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Récupère tous les versements d'une commande
    """
    # Vérifier que l'utilisateur a accès à cette commande
    order = await order_service.get_order(order_id, current_user.id if current_user.role == "client" else None)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")

    installments = await payment_installment_service.get_installments_by_order(order_id)
    return installments

@router.get("/{installment_id}", response_model=PaymentInstallmentPublic)
async def get_installment(
    installment_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Récupère un versement par son ID
    """
    installment = await payment_installment_service.get_installment_by_id(installment_id)
    if not installment:
        raise HTTPException(status_code=404, detail="Versement non trouvé")

    # Vérifier que l'utilisateur a accès à cette commande
    order = await order_service.get_order(installment.order_id, current_user.id if current_user.role == "client" else None)
    if not order:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    return installment

@router.post("/order/{order_id}/pay/{installment_id}")
async def pay_installment(
    order_id: str,
    installment_id: str,
    paid_amount: float,
    payment_method: PaymentMethod = PaymentMethod.CASH,
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Enregistre le paiement d'un versement
    """
    # Vérifier que l'utilisateur a accès à cette commande
    order = await order_service.get_order(order_id, current_user.id if current_user.role == "client" else None)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")

    # Vérifier que la commande est en versements
    if order.payment_type != PaymentType.INSTALLMENTS:
        raise HTTPException(status_code=400, detail="Cette commande n'est pas en versements")

    success = await order_service.pay_installment(
        order_id=order_id,
        installment_id=installment_id,
        paid_amount=paid_amount,
        payment_method=payment_method,
        paid_by=current_user.id
    )

    if not success:
        raise HTTPException(status_code=400, detail="Échec du paiement du versement")

    return {"message": "Versement payé avec succès"}

@router.delete("/{installment_id}")
async def cancel_installment(
    installment_id: str,
    reason: str = "",
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Annule un versement (admin/vendeur seulement)
    """
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    success = await payment_installment_service.cancel_installment(installment_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Versement non trouvé")

    return {"message": "Versement annulé"}

# === ROUTES POUR LES COMMANDES EN VERSEMENTS ===

@router.get("/users/search")
async def search_users_by_email(
    q: str = Query(..., description="Terme de recherche pour l'email"),
    limit: int = Query(10, description="Nombre maximum de résultats", le=50),
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Recherche les utilisateurs par email pour la sélection lors de la création de commande en versements
    (admin/vendeur seulement)
    """
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    # Rechercher les utilisateurs dont l'email contient le terme de recherche
    users = await user_service.list_users(q=q, limit=limit)

    # Retourner seulement les informations nécessaires pour la sélection
    user_options = [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name
        }
        for user in users
    ]

    return {"users": user_options, "count": len(user_options)}

@router.post("/create-order")
async def create_installment_order(
    installment_plan: InstallmentPlanCreate = Body(
        ...,
        example={
            "installments_count": 2,
            "first_payment_amount": 100,
            "installment_amount": 50,
            "due_dates": ["2025-10-03T06:49:20.788Z", "2025-11-03T06:49:20.788Z"],
            "customer_name": "John Doe",
            "customer_phone": "+2250102030405",
            "user_email": "client@example.com",
            "notes": "string"
        }
    ),
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Crée une commande avec paiement en versements en récupérant automatiquement les items du panier
    Si user_email est fourni, la commande est créée pour cet utilisateur existant (admin/vendeur seulement)
    """
    try:
        # Déterminer l'utilisateur pour lequel créer la commande
        target_user_id = current_user.id
        target_user_email = None
        cart_user_id = current_user.id  # Par défaut, utiliser le panier de l'utilisateur connecté

        if installment_plan.user_email:
            # Vérifier que l'utilisateur actuel est admin ou vendeur
            if current_user.role == "client":
                raise HTTPException(status_code=403, detail="Seuls les administrateurs et vendeurs peuvent créer des commandes pour d'autres utilisateurs")

            # Trouver l'utilisateur par email
            target_user = await user_service.get_user_by_email(installment_plan.user_email)
            if not target_user:
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé avec cet email")
            target_user_id = target_user.id
            target_user_email = target_user.email
            # Pour les achats en magasin, utiliser le panier du vendeur/admin, mais créer la commande pour le client
            # cart_user_id reste current_user.id (vendeur/admin)

        # Récupérer le panier de l'utilisateur qui fait l'achat (vendeur/admin)
        cart = await cart_service.get_cart(user_id=cart_user_id)
        if not cart or not cart.items:
            cart_user_desc = "votre" if cart_user_id == current_user.id else f"du vendeur {current_user.email}"
            raise HTTPException(status_code=400, detail=f"Le panier {cart_user_desc} est vide")

        # Calculer le total et préparer les items de commande
        total = 0.0
        order_items = []

        for item in cart.items:
            item_total = item.price * item.quantity
            total += item_total
            order_items.append({
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": item.price,
                "name": item.name,
                "images": item.images
            })

        # Recalculer le plan de versements basé sur le total réel du panier
        adjusted_installment_plan = await _adjust_installment_plan_for_total(
            installment_plan, total
        )

        # Préparer les données de commande
        order_data = {
            "items": order_items,
            "total": total,
            "status": "livree",
            "payment_status": "en_cours",
            "payment_method": "installments"
        }
        if adjusted_installment_plan.customer_name:
            order_data["customer_name"] = adjusted_installment_plan.customer_name
        if adjusted_installment_plan.customer_phone:
            order_data["customer_phone"] = adjusted_installment_plan.customer_phone

        # Créer la commande en versements
        order = await order_service.create_installment_order(
            user_id=target_user_id,
            order_data=order_data,
            installment_plan=adjusted_installment_plan,
            created_by=current_user.id
        )

        # La commande est livree immédiatement en boutique: sortir les articles du stock.
        for item in order_items:
            result = await db.products.update_one(
                {"_id": ObjectId(item["product_id"])},
                {"$inc": {"stock": -item["quantity"]}}
            )
            if result.matched_count == 0:
                logger.error(
                    "Produit %s introuvable pendant la sortie de stock de la commande %s",
                    item["product_id"],
                    order.id
                )

        # Vider le panier du vendeur/admin après création de la commande
        await cart_service.clear_cart(user_id=cart_user_id)

        user_desc = f"pour l'utilisateur {target_user_email}" if target_user_email else ""
        return {"order": order.model_dump(), "message": f"Commande en versements créée avec succès {user_desc}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/order/{order_id}/payment-summary")
async def get_order_payment_summary(
    order_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Récupère le résumé des paiements pour une commande
    """
    # Vérifier que l'utilisateur a accès à cette commande
    order = await order_service.get_order(order_id, current_user.id if current_user.role == "client" else None)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")

    summary = await order_service.get_order_payment_summary(order_id)
    return summary
