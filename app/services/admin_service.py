from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.db.mongo import db
from app.models.admin import AdminSettings, AdminSettingsUpdate

class AdminService:
    def __init__(self):
        self.users = db.users
        self.settings = db.settings
        self.orders = db.orders

    async def get_settings(self) -> AdminSettings:
        doc = await self.settings.find_one({})
        if not doc:
            now = datetime.utcnow()
            default = {
                "commission_rate": 0.1,
                "delivery_flat_fee": 5.0,
                "delivery_per_km": 0.5,
                "free_delivery_threshold": 100.0,
                "updated_at": now
            }
            await self.settings.insert_one(default)
            doc = default
        return AdminSettings(**doc)

    async def update_settings(self, data: AdminSettingsUpdate) -> AdminSettings:
        update = {k: v for k, v in data.dict().items() if v is not None}
        if not update:
            return await self.get_settings()
        update["updated_at"] = datetime.utcnow()
        await self.settings.update_one({}, {"$set": update}, upsert=True)
        return await self.get_settings()

    async def compute_commission_collected(self) -> float:
        settings = await self.get_settings()
        pipeline = [
            {"$match": {"payment_status": "effectue"}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        res = await self.orders.aggregate(pipeline).to_list(1)
        total = res[0]["total"] if res else 0.0
        return round(total * settings.commission_rate, 2)

    async def get_top_categories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Récupère les top catégories avec agrégation réelle"""
        pipeline = [
            {"$match": {"payment_status": "effectue"}},
            {"$unwind": "$items"},
            {"$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product"
            }},
            {"$unwind": "$product"},
            {"$lookup": {
                "from": "categories",
                "localField": "product.category_id", 
                "foreignField": "_id",
                "as": "category"
            }},
            {"$unwind": "$category"},
            {"$group": {
                "_id": "$product.category_id",
                "category_name": {"$first": "$category.name"},
                "total_revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}},
                "total_orders": {"$sum": 1},
                "total_quantity": {"$sum": "$items.quantity"}
            }},
            {"$sort": {"total_revenue": -1}},
            {"$limit": limit}
        ]
        
        categories = []
        async for cat in self.orders.aggregate(pipeline):
            categories.append({
                "category_id": str(cat["_id"]),
                "category_name": cat["category_name"],
                "total_revenue": cat["total_revenue"],
                "total_orders": cat["total_orders"],
                "total_quantity": cat["total_quantity"]
            })
        
        return categories

    async def get_commission_by_vendor(self) -> List[Dict[str, Any]]:
        """Commission détaillée par vendeur"""
        settings = await self.get_settings()
        
        pipeline = [
            {"$match": {"payment_status": "effectue"}},
            {"$unwind": "$items"},
            {"$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product"
            }},
            {"$unwind": "$product"},
            {"$group": {
                "_id": "$product.seller_id",
                "total_sales": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}},
                "total_orders": {"$sum": 1},
                "total_quantity": {"$sum": "$items.quantity"}
            }},
            {"$sort": {"total_sales": -1}}
        ]
        
        vendors = []
        async for vendor in self.orders.aggregate(pipeline):
            try:
                # Récupérer les infos du vendeur
                vendor_user = await self.users.find_one({"_id": ObjectId(vendor["_id"])})
                vendor_name = vendor_user.get("full_name", "Vendeur") if vendor_user else "Vendeur"
                
                commission = vendor["total_sales"] * settings.commission_rate
                
                vendors.append({
                    "vendor_id": str(vendor["_id"]),
                    "vendor_name": vendor_name,
                    "total_sales": vendor["total_sales"],
                    "total_orders": vendor["total_orders"],
                    "total_quantity": vendor["total_quantity"],
                    "commission_due": round(commission, 2),
                    "commission_rate": settings.commission_rate
                })
            except Exception:
                continue
        
        return vendors

    async def get_margin_stats(self) -> Dict[str, Any]:
        """Statistiques de marges globales"""
        # Calculer les remboursements traités pour les déduire du revenu
        refunds_collection = db.refunds
        processed_refunds_pipeline = [
            {"$match": {"status": "processed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        processed_refunds_result = await refunds_collection.aggregate(processed_refunds_pipeline).to_list(1)
        total_processed_refunds = processed_refunds_result[0]["total"] if processed_refunds_result else 0.0

        # Agrégation pour calculer revenus vs coûts
        pipeline = [
            {"$match": {"payment_status": "effectue"}},
            {"$unwind": "$items"},
            {"$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product"
            }},
            {"$unwind": "$product"},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}},
                "total_cost": {"$sum": {"$multiply": ["$product.cost_price", "$items.quantity"]}},
                "total_quantity": {"$sum": "$items.quantity"}
            }}
        ]

        result = await self.orders.aggregate(pipeline).to_list(1)

        if result:
            data = result[0]
            gross_revenue = data["total_revenue"]
            # Déduire les remboursements traités du revenu brut
            net_revenue = gross_revenue - total_processed_refunds
            cost = data["total_cost"]
            profit = net_revenue - cost
            margin_percent = (profit / net_revenue * 100) if net_revenue > 0 else 0

            return {
                "total_revenue": net_revenue,
                "total_cost": cost,
                "gross_profit": profit,
                "margin_percent": round(margin_percent, 2),
                "total_quantity": data["total_quantity"],
                "avg_profit_per_item": round(profit / data["total_quantity"], 2) if data["total_quantity"] > 0 else 0,
                "processed_refunds_deducted": total_processed_refunds
            }
        else:
            return {
                "total_revenue": -total_processed_refunds,  # Afficher les remboursements comme revenu négatif
                "total_cost": 0,
                "gross_profit": -total_processed_refunds,
                "margin_percent": 0,
                "total_quantity": 0,
                "avg_profit_per_item": 0,
                "processed_refunds_deducted": total_processed_refunds
            }

admin_service = AdminService()
