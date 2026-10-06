from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from app.models.promotion import (
    PromotionCreate, PromotionPublic, PromotionUpdate, PromotionListResponse
)
from app.models.user import UserPublic
from app.services.promotion_service import promotion_service
from app.api.auth import get_current_user, get_current_user_dependency

router = APIRouter(prefix="/promotions", tags=["promotions"])

def require_admin_user():
    async def admin_user_dependency(current_user: UserPublic = Depends(get_current_user_dependency)):
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Accès refusé. Rôle admin requis.")
        return current_user
    return admin_user_dependency

# === ENDPOINTS POUR LES PROMOTIONS ===

@router.post("/", response_model=PromotionPublic)
async def create_promotion(
    promotion: PromotionCreate,
    current_user: UserPublic = Depends(require_admin_user())
):
    """Crée une nouvelle promotion (Admin uniquement)."""
    try:
        created_promotion = await promotion_service.create_promotion(
            promotion, current_user.id
        )
        return created_promotion
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur création promotion: {str(e)}")

@router.get("/", response_model=PromotionListResponse)
async def get_promotions(
    skip: int = Query(0, ge=0, description="Nombre d'éléments à ignorer"),
    limit: int = Query(100, ge=1, le=1000, description="Nombre maximum d'éléments à retourner"),
    current_user: UserPublic = Depends(get_current_user_dependency)
):
    """Récupère toutes les promotions."""
    try:
        promotions = await promotion_service.get_all_promotions(skip=skip, limit=limit)
        total = len(promotions)  # Note: Pour une vraie pagination, il faudrait compter depuis la DB

        return PromotionListResponse(
            promotions=promotions,
            total=total,
            page=skip // limit,
            size=limit,
            has_next=total > skip + limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération promotions: {str(e)}")

@router.get("/{promotion_id}", response_model=PromotionPublic)
async def get_promotion(
    promotion_id: str,
    current_user: UserPublic = Depends(get_current_user_dependency)
):
    """Récupère une promotion par son ID."""
    try:
        promotion = await promotion_service.get_promotion(promotion_id)
        if not promotion:
            raise HTTPException(status_code=404, detail="Promotion non trouvée")
        return promotion
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération promotion: {str(e)}")

@router.get("/active", response_model=Optional[PromotionPublic])
async def get_active_promotion(
    current_user: UserPublic = Depends(get_current_user_dependency)
):
    """Récupère la promotion active en cours."""
    try:
        promotion = await promotion_service.get_active_promotion()
        return promotion
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération promotion active: {str(e)}")

@router.put("/{promotion_id}", response_model=PromotionPublic)
async def update_promotion(
    promotion_id: str,
    promotion_update: PromotionUpdate,
    current_user: UserPublic = Depends(require_admin_user())
):
    """Met à jour une promotion (Admin uniquement)."""
    try:
        updated_promotion = await promotion_service.update_promotion(
            promotion_id, promotion_update, current_user.id
        )
        if not updated_promotion:
            raise HTTPException(status_code=404, detail="Promotion non trouvée")
        return updated_promotion
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur mise à jour promotion: {str(e)}")

@router.delete("/{promotion_id}")
async def delete_promotion(
    promotion_id: str,
    current_user: UserPublic = Depends(require_admin_user())
):
    """Supprime une promotion (Admin uniquement)."""
    try:
        deleted = await promotion_service.delete_promotion(promotion_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Promotion non trouvée")
        return {"message": "Promotion supprimée avec succès"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur suppression promotion: {str(e)}")

@router.patch("/{promotion_id}/deactivate")
async def deactivate_promotion(
    promotion_id: str,
    current_user: UserPublic = Depends(require_admin_user())
):
    """Désactive une promotion (Admin uniquement)."""
    try:
        deactivated = await promotion_service.deactivate_promotion(promotion_id)
        if not deactivated:
            raise HTTPException(status_code=404, detail="Promotion non trouvée")
        return {"message": "Promotion désactivée avec succès"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur désactivation promotion: {str(e)}")

# === ENDPOINTS POUR LES CALCULS DE PRIX ===

@router.post("/calculate-discount")
async def calculate_discount(
    original_price: float,
    current_user: UserPublic = Depends(get_current_user_dependency)
):
    """Calcule le prix réduit pour un montant donné."""
    try:
        discounted_price, discount_amount = await promotion_service.calculate_discounted_price(original_price)

        return {
            "original_price": original_price,
            "discounted_price": discounted_price,
            "discount_amount": discount_amount,
            "has_discount": discounted_price < original_price
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul prix réduit: {str(e)}")
