from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from app.models.dashboard import InventoryAlert, InventoryStats, StockUpdate
from app.services.product_service import product_service
from app.api.auth import get_current_user
from app.models.user import UserPublic
from app.db.mongo import db
from app.models.product import ProductPublic

router = APIRouter(prefix="/inventory", tags=["inventory"])

@router.get("/low-stock", response_model=List[InventoryAlert])
async def get_low_stock_products(
    limit: int = Query(50, le=100),
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupère la liste des produits avec un stock faible"""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé")

    # Pas de filtrage par vendeur pour voir les données générales
    match_filter = {"is_active": True, "$expr": {"$lte": ["$stock", "$low_stock_threshold"]}}

    pipeline = [
        {"$match": match_filter},
        {"$limit": limit}
    ]

    alerts = []
    async for product in db.products.aggregate(pipeline):
        alerts.append(InventoryAlert(
            product_id=str(product["_id"]),
            product_name=product.get("name", "Produit"),
            current_stock=product.get("stock", 0),
            low_stock_threshold=product.get("low_stock_threshold", 0),
            seller_id=product.get("seller_id", "")
        ))

    return alerts

@router.get("/stats", response_model=InventoryStats)
async def get_inventory_stats(current_user: UserPublic = Depends(get_current_user)):
    """Statistiques générales de l'inventaire"""
    print(f"DEBUG: current_user.role = {current_user.role}")
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé")

    base_filter = {"is_active": True}
    # Pas de filtrage par vendeur pour voir les données générales

    # Nombre total de produits
    total_products = await db.products.count_documents(base_filter)

    # Produits en stock bas
    low_stock_filter = {**base_filter, "$expr": {"$lte": ["$stock", "$low_stock_threshold"]}}
    low_stock_count = await db.products.count_documents(low_stock_filter)

    # Produits en rupture de stock
    out_of_stock_filter = {**base_filter, "stock": 0}
    out_of_stock_count = await db.products.count_documents(out_of_stock_filter)

    # Valeur totale du stock
    stock_value_pipeline = [
        {"$match": base_filter},
        {"$group": {"_id": None, "total_value": {"$sum": {"$multiply": ["$price", "$stock"]}}}}
    ]
    stock_value_result = await db.products.aggregate(stock_value_pipeline).to_list(1)
    total_stock_value = stock_value_result[0]["total_value"] if stock_value_result else 0.0

    return InventoryStats(
        total_products=total_products,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        total_stock_value=total_stock_value,
        low_stock_percentage=(low_stock_count / total_products * 100) if total_products > 0 else 0
    )

@router.put("/stock/{product_id}", response_model=ProductPublic)
async def update_product_stock(
    product_id: str,
    stock_update: StockUpdate,
    current_user: UserPublic = Depends(get_current_user)
):
    """Met à jour le stock d'un produit (admin/vendeur uniquement)"""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Admin/Vendeur requis")

    try:
        # Vérifier que le produit existe
        existing_product = await db.products.find_one({"_id": product_id})
        if not existing_product:
            raise HTTPException(status_code=404, detail="Produit non trouvé")

        # Mettre à jour le stock
        update_result = await db.products.update_one(
            {"_id": product_id},
            {"$set": {"stock": stock_update.stock}}
        )

        if update_result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Échec de la mise à jour du stock")

        # Récupérer le produit mis à jour
        updated_product = await product_service.get_product(product_id)
        return updated_product

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour du stock: {str(e)}")
