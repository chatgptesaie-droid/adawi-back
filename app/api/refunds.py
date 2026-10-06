from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from app.models.refund import RefundCreate, RefundPublic, RefundUpdate, RefundStatus
from app.services.refund_service import refund_service
from app.api.auth import get_current_user
from app.models.user import UserPublic

router = APIRouter(prefix="/refunds", tags=["refunds"])

@router.post("/", response_model=RefundPublic)
async def create_refund(data: RefundCreate, current_user: UserPublic = Depends(get_current_user)):
    try:
        refund = await refund_service.create_refund(current_user.id, data)
        return refund
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[RefundPublic])
async def list_refunds(status: Optional[RefundStatus] = Query(None), skip: int = 0, limit: int = 50, current_user: UserPublic = Depends(get_current_user)):
    # Client: uniquement ses remboursements, Admin: tous, Vendeur: tous pour l'instant (pour simplifier)
    user_filter = None
    if current_user.role == "client":
        user_filter = current_user.id
    refunds = await refund_service.list_refunds(status=status.value if status else None, user_id=user_filter, skip=skip, limit=limit)
    return refunds

@router.get("/{refund_id}", response_model=RefundPublic)
async def get_refund(refund_id: str, current_user: UserPublic = Depends(get_current_user)):
    refund = await refund_service.get_refund(refund_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    if current_user.role == "client" and refund.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    return refund

@router.patch("/{refund_id}", response_model=RefundPublic)
async def update_refund(refund_id: str, data: RefundUpdate, current_user: UserPublic = Depends(get_current_user)):
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès admin/vendeur requis")
    updated = await refund_service.update_refund(refund_id, data, current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail="Refund not found")
    return updated

@router.get("/stats/summary")
async def refund_stats(current_user: UserPublic = Depends(get_current_user)):
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès admin/vendeur requis")
    return await refund_service.aggregate_stats()
