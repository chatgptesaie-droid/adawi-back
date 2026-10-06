from datetime import datetime, timedelta
from typing import List, Dict
from bson import ObjectId
from app.db.mongo import db
from app.models.dashboard import (
    AdminDashboardResponse, TopProduct, TopVendor,
    RecentOrder, OrderStatusCount, VendorDashboardResponse, PendingOrder, RefundStats
)
from app.models.order import OrderStatus, PaymentStatus, PaymentType
from app.services.analytics_service import analytics_service

class DashboardServiceFixed:
    def __init__(self):
        self.orders_collection = db.orders
        self.users_collection = db.users
        self.products_collection = db.products
        self.payment_installments_collection = db.payment_installments

    async def get_admin_dashboard(self) -> AdminDashboardResponse:
        """Récupère toutes les statistiques pour le dashboard admin avec données graphiques"""
        from datetime import timedelta

        # 1. KPIs principaux
        # Revenue from fully paid orders (excluding installment orders, which are counted via installments)
        revenue_pipeline = [
            {"$match": {
                "payment_status": PaymentStatus.effectue.value,
                "$or": [
                    {"payment_type": {"$ne": PaymentType.INSTALLMENTS.value}},
                    {"payment_type": {"$exists": False}}
                ]
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        revenue_result = await self.orders_collection.aggregate(revenue_pipeline).to_list(1)
        gross_revenue = revenue_result[0]["total"] if revenue_result else 0.0

        # Calculate total paid installments (all paid installments)
        installments_collection = db.payment_installments
        installments_pipeline = [
            {"$match": {"status": "paid"}},
            {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
        ]
        installments_result = await installments_collection.aggregate(installments_pipeline).to_list(1)
        total_installments_paid = installments_result[0]["total"] if installments_result else 0.0

        # Calculate processed refunds to deduct from revenue
        refunds_collection = db.refunds
        processed_refunds_pipeline = [
            {"$match": {"status": "processed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        processed_refunds_result = await refunds_collection.aggregate(processed_refunds_pipeline).to_list(1)
        total_processed_refunds = processed_refunds_result[0]["total"] if processed_refunds_result else 0.0

        # Net revenue = Gross revenue + Installments paid - Processed refunds
        total_revenue = gross_revenue + total_installments_paid - total_processed_refunds

        total_orders = await self.orders_collection.count_documents({})
        total_customers = await self.users_collection.count_documents({"role": "client"})
        total_vendors = await self.users_collection.count_documents({"role": "vendeur"})
        total_products = await self.products_collection.count_documents({})

        # Commission collectée
        from app.services.admin_service import admin_service
        commission_collected = await admin_service.compute_commission_collected()

        # === Refunds stats (Phase 7 part 1) ===
        refunds_coll = db.refunds
        refunds_count = await refunds_coll.count_documents({})
        # Only count processed refunds for total amount (consistent with revenue calculation)
        refunds_total_pipeline = [
            {"$match": {"status": "processed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        refunds_total_res = await refunds_coll.aggregate(refunds_total_pipeline).to_list(1)
        refunds_total_amount = refunds_total_res[0]["total"] if refunds_total_res else 0.0

        # Stats détaillées remboursements par statut
        refunds_by_status = await refunds_coll.aggregate([
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]).to_list(10)

        refund_stats_dict = {"pending": 0, "approved": 0, "rejected": 0, "processed": 0}
        for stat in refunds_by_status:
            refund_stats_dict[stat["_id"]] = stat["count"]

        # === Calculs coûts et marges (Phase 7) ===
        # Agrégation des coûts totaux sur commandes payées
        cost_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value}},
            {"$unwind": "$items"},
            {"$lookup": {"from": "products", "localField": "items.product_id", "foreignField": "_id", "as": "product"}},
            {"$unwind": "$product"},
            {"$group": {"_id": None, "total_cost": {"$sum": {"$multiply": ["$product.cost_price", "$items.quantity"]}}}}
        ]
        cost_result = await self.orders_collection.aggregate(cost_pipeline).to_list(1)
        total_cost = cost_result[0]["total_cost"] if cost_result else 0.0

        gross_profit = total_revenue - total_cost
        gross_margin_percent = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0.0

        # === Alertes stock bas (Phase 7) ===
        low_stock_pipeline = [
            {"$match": {"is_active": True, "$expr": {"$lte": ["$stock", "$low_stock_threshold"]}}},
            {"$count": "low_stock_count"}
        ]
        low_stock_result = await self.products_collection.aggregate(low_stock_pipeline).to_list(1)
        low_stock_products = low_stock_result[0]["low_stock_count"] if low_stock_result else 0

        # Calculate average low_stock_threshold
        threshold_pipeline = [
            {"$match": {"is_active": True}},
            {"$group": {"_id": None, "avg_threshold": {"$avg": "$low_stock_threshold"}}}
        ]
        threshold_result = await self.products_collection.aggregate(threshold_pipeline).to_list(1)
        low_stock_threshold = threshold_result[0]["avg_threshold"] if threshold_result and threshold_result[0]["avg_threshold"] else 0.0

        # Calculate out of stock count
        out_of_stock_pipeline = [
            {"$match": {"is_active": True, "stock": 0}},
            {"$count": "out_of_stock_count"}
        ]
        out_of_stock_result = await self.products_collection.aggregate(out_of_stock_pipeline).to_list(1)
        out_of_stock_count = out_of_stock_result[0]["out_of_stock_count"] if out_of_stock_result else 0

        # Liste produits en alerte stock
        inventory_alerts_pipeline = [
            {"$match": {"is_active": True, "$expr": {"$lte": ["$stock", "$low_stock_threshold"]}}},
            {"$limit": 10}
        ]
        inventory_alerts = []
        async for product in self.products_collection.aggregate(inventory_alerts_pipeline):
            from app.models.dashboard import InventoryAlert
            inventory_alerts.append(InventoryAlert(
                product_id=str(product["_id"]),
                product_name=product.get("name", "Produit"),
                current_stock=product.get("stock", 0),
                low_stock_threshold=product.get("low_stock_threshold", 0),
                seller_id=product.get("seller_id", "")
            ))

        # === Évolution revenus vs coûts (30 derniers jours) ===
        cost_revenue_evolution = []
        for i in range(30):
            day = datetime.utcnow() - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            # Revenue du jour (gross)
            day_revenue_pipeline = [
                {"$match": {
                    "payment_status": PaymentStatus.effectue.value,
                    "created_at": {"$gte": day_start, "$lt": day_end},
                    "$or": [
                        {"payment_type": {"$ne": PaymentType.INSTALLMENTS.value}},
                        {"payment_type": {"$exists": False}}
                    ]
                }},
                {"$group": {"_id": None, "revenue": {"$sum": "$total"}}}
            ]
            day_revenue_result = await self.orders_collection.aggregate(day_revenue_pipeline).to_list(1)
            day_gross_revenue = day_revenue_result[0]["revenue"] if day_revenue_result else 0.0

            # Processed refunds for the day
            day_refunds_pipeline = [
                {"$match": {"status": "processed", "updated_at": {"$gte": day_start, "$lt": day_end}}},
                {"$group": {"_id": None, "refunds": {"$sum": "$amount"}}}
            ]
            day_refunds_result = await refunds_collection.aggregate(day_refunds_pipeline).to_list(1)
            day_processed_refunds = day_refunds_result[0]["refunds"] if day_refunds_result else 0.0

            # Net revenue for the day
            day_revenue = day_gross_revenue - day_processed_refunds

            # Coût du jour
            day_cost_pipeline = [
                {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": day_start, "$lt": day_end}}},
                {"$unwind": "$items"},
                {"$lookup": {"from": "products", "localField": "items.product_id", "foreignField": "_id", "as": "product"}},
                {"$unwind": "$product"},
                {"$group": {"_id": None, "cost": {"$sum": {"$multiply": ["$product.cost_price", "$items.quantity"]}}}}
            ]
            day_cost_result = await self.orders_collection.aggregate(day_cost_pipeline).to_list(1)
            day_cost = day_cost_result[0]["cost"] if day_cost_result else 0.0

            # Paid installments for the day
            day_installments_pipeline = [
                {"$match": {"status": "paid", "paid_at": {"$gte": day_start, "$lt": day_end}}},
                {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
            ]
            day_installments_result = await db.payment_installments.aggregate(day_installments_pipeline).to_list(1)
            day_installments_paid = day_installments_result[0]["total"] if day_installments_result else 0.0

            # Net revenue for the day including installments
            day_revenue = day_gross_revenue + day_installments_paid - day_processed_refunds

            day_profit = day_revenue - day_cost
            day_margin = (day_profit / day_revenue * 100) if day_revenue > 0 else 0.0

            cost_revenue_evolution.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "revenue": day_revenue,
                "cost": day_cost,
                "profit": day_profit,
                "margin_percent": day_margin
            })

        cost_revenue_evolution.reverse()  # Ordre chronologique

        # 2. Croissance (comparaison avec période précédente - 30 jours)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        sixty_days_ago = datetime.utcnow() - timedelta(days=60)

        # Revenue actuel vs précédent (gross)
        current_revenue_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        current_revenue_result = await self.orders_collection.aggregate(current_revenue_pipeline).to_list(1)
        current_gross_revenue = current_revenue_result[0]["total"] if current_revenue_result else 0.0

        previous_revenue_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": sixty_days_ago, "$lt": thirty_days_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        previous_revenue_result = await self.orders_collection.aggregate(previous_revenue_pipeline).to_list(1)
        previous_gross_revenue = previous_revenue_result[0]["total"] if previous_revenue_result else 0.0

        # Calculate refunds for current period
        current_refunds_pipeline = [
            {"$match": {"status": "processed", "updated_at": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        current_refunds_result = await refunds_collection.aggregate(current_refunds_pipeline).to_list(1)
        current_refunds = current_refunds_result[0]["total"] if current_refunds_result else 0.0

        # Calculate refunds for previous period
        previous_refunds_pipeline = [
            {"$match": {"status": "processed", "updated_at": {"$gte": sixty_days_ago, "$lt": thirty_days_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        previous_refunds_result = await refunds_collection.aggregate(previous_refunds_pipeline).to_list(1)
        previous_refunds = previous_refunds_result[0]["total"] if previous_refunds_result else 0.0

        # Net revenue calculations
        current_revenue = current_gross_revenue - current_refunds
        previous_revenue = previous_gross_revenue - previous_refunds

        revenue_growth = ((current_revenue - previous_revenue) / previous_revenue * 100) if previous_revenue > 0 else 0

        # Croissance commandes
        current_orders = await self.orders_collection.count_documents({"created_at": {"$gte": thirty_days_ago}})
        previous_orders = await self.orders_collection.count_documents({"created_at": {"$gte": sixty_days_ago, "$lt": thirty_days_ago}})
        orders_growth = ((current_orders - previous_orders) / previous_orders * 100) if previous_orders > 0 else 0

        # Croissance clients
        current_customers = await self.users_collection.count_documents({"role": "client", "created_at": {"$gte": thirty_days_ago}})
        previous_customers = await self.users_collection.count_documents({"role": "client", "created_at": {"$gte": sixty_days_ago, "$lt": thirty_days_ago}})
        customers_growth = ((current_customers - previous_customers) / previous_customers * 100) if previous_customers > 0 else 0

        # 3. Évolution du CA (30 derniers jours)
        revenue_evolution = []
        for i in range(30):
            day = datetime.utcnow() - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            day_revenue_pipeline = [
                {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": day_start, "$lt": day_end}}},
                {"$group": {"_id": None, "revenue": {"$sum": "$total"}, "count": {"$sum": 1}}}
            ]
            day_result = await self.orders_collection.aggregate(day_revenue_pipeline).to_list(1)

            # Calculate processed refunds for the day
            day_refunds_pipeline = [
                {"$match": {"status": "processed", "updated_at": {"$gte": day_start, "$lt": day_end}}},
                {"$group": {"_id": None, "refunds": {"$sum": "$amount"}}}
            ]
            day_refunds_result = await refunds_collection.aggregate(day_refunds_pipeline).to_list(1)
            day_processed_refunds = day_refunds_result[0]["refunds"] if day_refunds_result else 0.0

            # Paid installments for the day
            day_installments_pipeline = [
                {"$match": {"status": "paid", "paid_at": {"$gte": day_start, "$lt": day_end}}},
                {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
            ]
            day_installments_result = await db.payment_installments.aggregate(day_installments_pipeline).to_list(1)
            day_installments_paid = day_installments_result[0]["total"] if day_installments_result else 0.0

            if day_result:
                gross_revenue = day_result[0]["revenue"]
                net_revenue = gross_revenue + day_installments_paid - day_processed_refunds
                revenue_evolution.append({
                    "date": day_start.strftime("%Y-%m-%d"),
                    "revenue": net_revenue,
                    "orders_count": day_result[0]["count"]
                })
            else:
                revenue_evolution.append({
                    "date": day_start.strftime("%Y-%m-%d"),
                    "revenue": day_installments_paid - day_processed_refunds,  # Include installments even if no orders
                    "orders_count": 0
                })

        revenue_evolution.reverse()  # Ordre chronologique

        # 4. Ventes par catégorie
        sales_by_category = []

        # Récupérer toutes les catégories depuis la collection categories
        categories_collection = self.products_collection.database.categories
        async for category_doc in categories_collection.find({}):
            category_id = str(category_doc["_id"])
            category_name = category_doc.get("name", f"Catégorie {category_id}")

            # Calculer les ventes pour cette catégorie
            category_sales_pipeline = [
                {"$unwind": "$items"},
                {"$addFields": {
                    "items.product_id_obj": {
                        "$convert": {
                            "input": "$items.product_id",
                            "to": "objectId",
                            "onError": None  # Retourne null si conversion échoue
                        }
                    }
                }},
                {"$match": {"items.product_id_obj": {"$ne": None}}},  # Filtrer les conversions échouées
                {"$lookup": {"from": "products", "localField": "items.product_id_obj", "foreignField": "_id", "as": "product"}},
                {"$unwind": "$product"},
                {"$match": {"product.category_id": category_id, "payment_status": PaymentStatus.effectue.value}},
                {"$group": {"_id": None, "total_sales": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}, "count": {"$sum": 1}}}
            ]
            category_result = await self.orders_collection.aggregate(category_sales_pipeline).to_list(1)

            if category_result:
                percentage = (category_result[0]["total_sales"] / total_revenue * 100) if total_revenue > 0 else 0
                sales_by_category.append({
                    "category_name": category_name,
                    "total_sales": category_result[0]["total_sales"],
                    "product_count": category_result[0]["count"],
                    "percentage": percentage
                })
            else:
                # Catégorie sans ventes
                sales_by_category.append({
                    "category_name": category_name,
                    "total_sales": 0.0,
                    "product_count": 0,
                    "percentage": 0.0
                })

        # 5. Croissance utilisateurs (12 derniers mois)
        user_growth = []
        for i in range(12):
            month_start = (datetime.utcnow().replace(day=1) - timedelta(days=30*i)).replace(hour=0, minute=0, second=0, microsecond=0)
            month_end = month_start + timedelta(days=30)

            new_clients = await self.users_collection.count_documents({
                "role": "client",
                "created_at": {"$gte": month_start, "$lt": month_end}
            })
            new_vendors = await self.users_collection.count_documents({
                "role": "vendeur",
                "created_at": {"$gte": month_start, "$lt": month_end}
            })
            total_users_month = await self.users_collection.count_documents({
                "created_at": {"$lt": month_end}
            })

            user_growth.append({
                "date": month_start.strftime("%Y-%m"),
                "new_clients": new_clients,
                "new_vendors": new_vendors,
                "total_users": total_users_month
            })

        user_growth.reverse()

        # 6. Ventes géographiques (simulation - à adapter selon vos données)
        geographic_sales = [
            {"region": "Paris", "sales_count": 45, "revenue": 2500.0},
            {"region": "Lyon", "sales_count": 32, "revenue": 1800.0},
            {"region": "Marseille", "sales_count": 28, "revenue": 1600.0},
            {"region": "Toulouse", "sales_count": 21, "revenue": 1200.0},
            {"region": "Autres", "sales_count": 74, "revenue": 4200.0}
        ]

        # Récupération des données existantes (code existant)...
        top_products_pipeline = [
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.product_id",
                "name": {"$first": "$items.name"},
                "total_quantity": {"$sum": "$items.quantity"},
                "total_revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}
            }},
            {"$sort": {"total_quantity": -1}},
            {"$limit": 5}
        ]
        top_products_cursor = self.orders_collection.aggregate(top_products_pipeline)
        top_products = []
        async for product in top_products_cursor:
            top_products.append(TopProduct(
                product_id=str(product["_id"]),
                name=product["name"],
                total_quantity=product["total_quantity"],
                total_revenue=product["total_revenue"]
            ))

        top_vendors_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "user_id": {"$regex": "^[a-fA-F0-9]{24}$"}}},
            {"$group": {
                "_id": "$user_id",
                "total_orders": {"$sum": 1},
                "total_revenue": {"$sum": "$total"}
            }},
            {"$sort": {"total_revenue": -1}},
            {"$limit": 5}
        ]
        top_vendors_cursor = self.orders_collection.aggregate(top_vendors_pipeline)
        top_vendors = []
        async for vendor in top_vendors_cursor:
            try:
                user = await self.users_collection.find_one({"_id": ObjectId(vendor["_id"])})
                user_name = user.get("full_name", "Utilisateur") if user else "Utilisateur"
                if user_name is None:
                    user_name = "Utilisateur"
            except:
                user_name = "Utilisateur"
            top_vendors.append(TopVendor(
                user_id=str(vendor["_id"]),
                name=user_name,
                total_orders=vendor["total_orders"],
                total_revenue=vendor["total_revenue"]
            ))

        recent_orders_cursor = self.orders_collection.find().sort("created_at", -1).limit(5)
        recent_orders = []
        async for order in recent_orders_cursor:
            try:
                user = await self.users_collection.find_one({"_id": ObjectId(order["user_id"])})
                user_name = user.get("full_name", "Utilisateur") if user else "Utilisateur"
                if user_name is None:
                    user_name = "Utilisateur"
            except:
                user_name = "Utilisateur"
            recent_orders.append(RecentOrder(
                order_id=str(order["_id"]),
                user_name=user_name,
                total=order.get("total", 0),
                status=order["status"],
                created_at=order["created_at"]
            ))

        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        status_cursor = self.orders_collection.aggregate(status_pipeline)
        orders_by_status = []
        async for status in status_cursor:
            orders_by_status.append(OrderStatusCount(
                status=status["_id"],
                count=status["count"]
            ))

        pending_cursor = self.orders_collection.find({"status": {"$nin": [OrderStatus.livree.value, OrderStatus.annulee.value]}}).sort("created_at", -1)
        pending_orders = []
        async for order in pending_cursor:
            try:
                user = await self.users_collection.find_one({"_id": ObjectId(order["user_id"])})
                user_name = user.get("full_name", "Utilisateur") if user else "Utilisateur"
                if user_name is None:
                    user_name = "Utilisateur"
            except:
                user_name = "Utilisateur"
            pending_orders.append(PendingOrder(
                order_id=str(order["_id"]),
                user_name=user_name,
                status=order["status"],
                created_at=order["created_at"],
                total=order.get("total", 0)
            ))

        # Calculs pour les nouveaux champs
        week_ago = datetime.utcnow() - timedelta(days=7)
        revenue_semaine_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": week_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        revenue_semaine_result = await self.orders_collection.aggregate(revenue_semaine_pipeline).to_list(1)
        total_revenue_semaine = revenue_semaine_result[0]["total"] if revenue_semaine_result else 0.0

        two_weeks_ago = datetime.utcnow() - timedelta(days=14)
        revenue_previous_semaine_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": two_weeks_ago, "$lt": week_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        revenue_previous_result = await self.orders_collection.aggregate(revenue_previous_semaine_pipeline).to_list(1)
        revenue_previous_semaine = revenue_previous_result[0]["total"] if revenue_previous_result else 0.0
        pourcentage_revenue_semaine = (total_revenue_semaine / revenue_previous_semaine * 100) if revenue_previous_semaine > 0 else 0.0

        # Orders semaine - inclut toutes les commandes payées (en ligne + physiques)
        orders_semaine_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": week_ago}}},
            {"$count": "total_orders"}
        ]
        orders_semaine_result = await self.orders_collection.aggregate(orders_semaine_pipeline).to_list(1)
        total_commande_semaine = orders_semaine_result[0]["total_orders"] if orders_semaine_result else 0

        orders_previous_semaine_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": two_weeks_ago, "$lt": week_ago}}},
            {"$count": "total_orders"}
        ]
        orders_previous_result = await self.orders_collection.aggregate(orders_previous_semaine_pipeline).to_list(1)
        orders_previous_semaine = orders_previous_result[0]["total_orders"] if orders_previous_result else 0
        pourcentage_commande_semaine = (total_commande_semaine / orders_previous_semaine * 100) if orders_previous_semaine > 0 else 0.0

        # Statistiques journalières et hebdomadaires pour admin
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        week_ago = today - timedelta(days=7)

        # Commandes aujourd'hui (toutes les commandes créées aujourd'hui)
        today_orders_pipeline = [
            {"$match": {"created_at": {"$gte": today, "$lt": tomorrow}}},
            {"$count": "total_orders_today"}
        ]
        today_orders_result = await self.orders_collection.aggregate(today_orders_pipeline).to_list(1)
        total_orders_today = today_orders_result[0]["total_orders_today"] if today_orders_result else 0

        # Commandes cette semaine (toutes les commandes créées cette semaine)
        week_orders_pipeline = [
            {"$match": {"created_at": {"$gte": week_ago}}},
            {"$count": "total_orders_week"}
        ]
        week_orders_result = await self.orders_collection.aggregate(week_orders_pipeline).to_list(1)
        total_orders_week = week_orders_result[0]["total_orders_week"] if week_orders_result else 0

        # Revenus aujourd'hui (brut pour commandes payées aujourd'hui)
        today_revenue_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": today, "$lt": tomorrow}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        today_revenue_result = await self.orders_collection.aggregate(today_revenue_pipeline).to_list(1)
        today_gross_revenue = today_revenue_result[0]["total"] if today_revenue_result else 0.0

        # Paid installments today
        today_installments_pipeline = [
            {"$match": {"status": "paid", "paid_at": {"$gte": today, "$lt": tomorrow}}},
            {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
        ]
        today_installments_result = await db.payment_installments.aggregate(today_installments_pipeline).to_list(1)
        today_installments_paid = today_installments_result[0]["total"] if today_installments_result else 0.0

        # Remboursements traités aujourd'hui
        today_refunds_pipeline = [
            {"$match": {"status": "processed", "updated_at": {"$gte": today, "$lt": tomorrow}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        today_refunds_result = await refunds_collection.aggregate(today_refunds_pipeline).to_list(1)
        today_processed_refunds = today_refunds_result[0]["total"] if today_refunds_result else 0.0

        # Revenu net aujourd'hui
        total_revenue_today = today_gross_revenue + today_installments_paid - today_processed_refunds

        # Revenus cette semaine (brut pour commandes payées cette semaine)
        week_revenue_pipeline = [
            {"$match": {"payment_status": PaymentStatus.effectue.value, "created_at": {"$gte": week_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        week_revenue_result = await self.orders_collection.aggregate(week_revenue_pipeline).to_list(1)
        week_gross_revenue = week_revenue_result[0]["total"] if week_revenue_result else 0.0

        # Paid installments this week
        week_installments_pipeline = [
            {"$match": {"status": "paid", "paid_at": {"$gte": week_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
        ]
        week_installments_result = await db.payment_installments.aggregate(week_installments_pipeline).to_list(1)
        week_installments_paid = week_installments_result[0]["total"] if week_installments_result else 0.0

        # Remboursements traités cette semaine
        week_refunds_pipeline = [
            {"$match": {"status": "processed", "updated_at": {"$gte": week_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        week_refunds_result = await refunds_collection.aggregate(week_refunds_pipeline).to_list(1)
        week_processed_refunds = week_refunds_result[0]["total"] if week_refunds_result else 0.0

        # Revenu net cette semaine
        total_revenue_week = week_gross_revenue + week_installments_paid - week_processed_refunds

        # Statistiques visiteurs
        try:
            visitor_stats_all = await analytics_service.get_visitor_stats(365)
            total_visiteurs = visitor_stats_all.unique_visitors
        except:
            total_visiteurs = 0

        try:
            visitor_stats_current = await analytics_service.get_visitor_stats(7)
            total_visiteurs_semaine = visitor_stats_current.unique_visitors
        except:
            total_visiteurs_semaine = 0

        try:
            visitor_stats_previous = await analytics_service.get_visitor_stats(14)
            total_visiteurs_previous_semaine = visitor_stats_previous.unique_visitors - total_visiteurs_semaine
            pourcentage_visiteurs_semaine = (total_visiteurs_semaine / total_visiteurs_previous_semaine * 100) if total_visiteurs_previous_semaine > 0 else 0.0
        except:
            pourcentage_visiteurs_semaine = 0.0

        # Pourcentage visiteurs total par rapport au mois dernier
        try:
            now = datetime.utcnow()
            last_month_end = now.replace(day=1) - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            visitors_last_month = len(await db.visitors.distinct("ip_hash", {
                "timestamp": {"$gte": last_month_start, "$lt": last_month_end + timedelta(days=1)}
            }))
            pourcentage_visiteur_total = (total_visiteurs / visitors_last_month * 100) if visitors_last_month > 0 else 0.0
        except:
            pourcentage_visiteur_total = 0.0

        prix_total_rembourse = refunds_total_amount
        revenus_par_categorie = {item["category_name"]: item["total_sales"] for item in sales_by_category}
        revenus_par_categorie_percent = {item["category_name"]: item["percentage"] for item in sales_by_category}
        top_categorie = max(revenus_par_categorie, key=revenus_par_categorie.get) if revenus_par_categorie else None
        top_categorie_revenue = revenus_par_categorie.get(top_categorie) if top_categorie else None

        return AdminDashboardResponse(
            # KPIs principaux
            total_revenue=total_revenue,
            total_orders=total_orders,
            total_customers=total_customers,
            total_vendors=total_vendors,
            total_products=total_products,
            commission_collected=commission_collected,

            # PHASE 7 - Nouveaux KPIs
            total_cost=total_cost,
            gross_profit=gross_profit,
            gross_margin_percent=gross_margin_percent,
            refunds_count=refunds_count,
            refunds_total_amount=refunds_total_amount,
            low_stock_products=low_stock_products,
            low_stock_threshold=low_stock_threshold,
            out_of_stock_count=out_of_stock_count,

            # Croissance
            revenue_growth=revenue_growth,
            orders_growth=orders_growth,
            customers_growth=customers_growth,

            # Nouveaux champs demandés
            total_revenue_semaine=total_revenue_semaine,
            pourcentage_revenue_semaine=pourcentage_revenue_semaine,
            total_visiteurs=total_visiteurs,
            total_visiteurs_semaine=total_visiteurs_semaine,
            pourcentage_visiteurs_semaine=pourcentage_visiteurs_semaine,
            pourcentage_visiteur_total=pourcentage_visiteur_total,
            prix_total_rembourse=prix_total_rembourse,
            revenus_par_categorie=revenus_par_categorie,
            revenus_par_categorie_percent=revenus_par_categorie_percent,
            top_categorie=top_categorie,
            top_categorie_revenue=top_categorie_revenue,
            total_commande_semaine=total_commande_semaine,
            pourcentage_commande_semaine=pourcentage_commande_semaine,

            # Statistiques journalières et hebdomadaires
            total_orders_today=total_orders_today,
            total_orders_week=total_orders_week,
            total_revenue_today=total_revenue_today,
            total_revenue_week=total_revenue_week,

            # Données graphiques
            revenue_evolution=revenue_evolution,
            cost_revenue_evolution=cost_revenue_evolution,
            sales_by_category=sales_by_category,
            user_growth=user_growth,
            geographic_sales=geographic_sales,

            # Stats remboursements et inventaire
            refund_stats=RefundStats(
                total_refunds=refunds_count,
                total_refunded_amount=refunds_total_amount,
                pending_refunds=refund_stats_dict.get("pending", 0),
                approved_refunds=refund_stats_dict.get("approved", 0),
                rejected_refunds=refund_stats_dict.get("rejected", 0),
                processed_refunds=refund_stats_dict.get("processed", 0)
            ),
            inventory_alerts=inventory_alerts,

            # Données existantes
            top_products=top_products,
            top_vendors=top_vendors,
            recent_orders=recent_orders,
            orders_by_status=orders_by_status,
            pending_orders=pending_orders
        )

    async def get_vendor_dashboard(self, vendor_id: str) -> VendorDashboardResponse:
        """Récupère les statistiques pour le dashboard d'un vendeur spécifique - comme l'admin"""

        # 1. Récupérer tous les produits du vendeur
        vendor_products = await self.products_collection.find({"seller_id": vendor_id}).to_list(None)
        vendor_product_ids = [str(p["_id"]) for p in vendor_products]

        # 2. Chiffre d'affaires total (commandes payées complètes + versements payés)
        # Revenue from fully paid orders (excluding installment orders)
        revenue_pipeline = [
            {"$match": {
                "payment_status": PaymentStatus.effectue.value,
                "$or": [
                    {"payment_type": {"$ne": PaymentType.INSTALLMENTS.value}},
                    {"payment_type": {"$exists": False}}
                ]
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        revenue_result = await self.orders_collection.aggregate(revenue_pipeline).to_list(1)
        gross_revenue = revenue_result[0]["total"] if revenue_result else 0.0

        # Calculate total paid installments
        installments_collection = db.payment_installments
        installments_pipeline = [
            {"$match": {"status": "paid"}},
            {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
        ]
        installments_result = await installments_collection.aggregate(installments_pipeline).to_list(1)
        total_installments_paid = installments_result[0]["total"] if installments_result else 0.0

        # Calculate processed refunds to deduct from revenue
        refunds_collection = db.refunds
        processed_refunds_pipeline = [
            {"$match": {"status": "processed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        processed_refunds_result = await refunds_collection.aggregate(processed_refunds_pipeline).to_list(1)
        total_processed_refunds = processed_refunds_result[0]["total"] if processed_refunds_result else 0.0

        # Net revenue = Gross revenue + Installments paid - Processed refunds
        total_revenue = gross_revenue + total_installments_paid - total_processed_refunds

        # 3. Nombre total de commandes
        total_orders = await self.orders_collection.count_documents({})

        # 4. Nombre total de produits (général)
        total_products = await self.products_collection.count_documents({})

        # 5. Top produits (général)
        top_products_pipeline = [
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.product_id",
                "name": {"$first": "$items.name"},
                "total_quantity": {"$sum": "$items.quantity"},
                "total_revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}
            }},
            {"$sort": {"total_quantity": -1}},
            {"$limit": 5}
        ]
        top_products_cursor = self.orders_collection.aggregate(top_products_pipeline)
        top_products = []
        async for product in top_products_cursor:
            top_products.append(TopProduct(
                product_id=str(product["_id"]),
                name=product["name"],
                total_quantity=product["total_quantity"],
                total_revenue=product["total_revenue"]
            ))

        # 6. Commandes récentes (toutes les commandes)
        recent_orders_cursor = self.orders_collection.find().sort("created_at", -1).limit(5)
        recent_orders = []
        async for order in recent_orders_cursor:
            try:
                user = await self.users_collection.find_one({"_id": ObjectId(order["user_id"])})
                user_name = user.get("full_name", "Utilisateur") if user else "Utilisateur"
                if user_name is None:
                    user_name = "Utilisateur"
            except:
                user_name = "Utilisateur"
            recent_orders.append(RecentOrder(
                order_id=str(order["_id"]),
                user_name=user_name,
                total=order.get("total", 0),
                status=order["status"],
                created_at=order["created_at"]
            ))

        # 7. Commandes par statut (toutes les commandes)
        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        status_cursor = self.orders_collection.aggregate(status_pipeline)
        orders_by_status = []
        async for status in status_cursor:
            orders_by_status.append(OrderStatusCount(
                status=status["_id"],
                count=status["count"]
            ))

        # 8. Panier moyen
        average_order_value = total_revenue / total_orders if total_orders > 0 else 0.0

        # 9. Statistiques journalières et hebdomadaires
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = datetime.utcnow() - timedelta(days=7)
        month_ago = datetime.utcnow() - timedelta(days=30)
        tomorrow = today_start + timedelta(days=1)

        # Commandes aujourd'hui (toutes les commandes créées aujourd'hui)
        today_orders_pipeline = [
            {"$match": {"created_at": {"$gte": today_start, "$lt": tomorrow}}},
            {"$count": "total_orders_today"}
        ]
        today_orders_result = await self.orders_collection.aggregate(today_orders_pipeline).to_list(1)
        total_orders_today = today_orders_result[0]["total_orders_today"] if today_orders_result else 0

        # Commandes cette semaine (toutes les commandes créées cette semaine)
        week_orders_pipeline = [
            {"$match": {"created_at": {"$gte": week_ago}}},
            {"$count": "total_orders_week"}
        ]
        week_orders_result = await self.orders_collection.aggregate(week_orders_pipeline).to_list(1)
        total_orders_week = week_orders_result[0]["total_orders_week"] if week_orders_result else 0

        # Commandes ce mois (toutes les commandes créées ce mois)
        month_orders_pipeline = [
            {"$match": {"created_at": {"$gte": month_ago}}},
            {"$count": "total_orders_month"}
        ]
        month_orders_result = await self.orders_collection.aggregate(month_orders_pipeline).to_list(1)
        total_orders_month = month_orders_result[0]["total_orders_month"] if month_orders_result else 0

        # Revenus aujourd'hui (brut pour commandes payées complètes, excluant les versements)
        today_revenue_pipeline = [
            {"$match": {
                "payment_status": PaymentStatus.effectue.value,
                "created_at": {"$gte": today_start, "$lt": tomorrow}
                # "$or": [
                #     {"payment_type": {"$ne": PaymentType.INSTALLMENTS.value}},
                #     {"payment_type": {"$exists": False}}
                # ]
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        today_revenue_result = await self.orders_collection.aggregate(today_revenue_pipeline).to_list(1)
        today_gross_revenue = today_revenue_result[0]["total"] if today_revenue_result else 0.0

        # Paid installments today
        today_installments_pipeline = [
            {"$match": {"status": "paid", "paid_at": {"$gte": today_start, "$lt": tomorrow}}}
        ]
        today_installments_result = await self.payment_installments_collection.aggregate([
            {"$match": {"status": "paid", "paid_at": {"$gte": today_start, "$lt": tomorrow}}},
            {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
        ]).to_list(1)
        today_installments_paid = today_installments_result[0]["total"] if today_installments_result else 0.0

        # Remboursements traités aujourd'hui
        today_refunds_pipeline = [
            {"$match": {"status": "processed", "updated_at": {"$gte": today_start, "$lt": tomorrow}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        today_refunds_result = await db.refunds.aggregate(today_refunds_pipeline).to_list(1)
        today_processed_refunds = today_refunds_result[0]["total"] if today_refunds_result else 0.0

        # Revenu net aujourd'hui
        total_revenue_today = today_gross_revenue + today_installments_paid - today_processed_refunds

        # Revenus cette semaine (brut pour commandes payées complètes, excluant les versements)
        week_revenue_pipeline = [
            {"$match": {
                "payment_status": PaymentStatus.effectue.value,
                "created_at": {"$gte": week_ago}
                # "$or": [
                #     {"payment_type": {"$ne": PaymentType.INSTALLMENTS.value}},
                #     {"payment_type": {"$exists": False}}
                # ]
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        week_revenue_result = await self.orders_collection.aggregate(week_revenue_pipeline).to_list(1)
        week_gross_revenue = week_revenue_result[0]["total"] if week_revenue_result else 0.0

        # Paid installments this week
        week_installments_result = await self.payment_installments_collection.aggregate([
            {"$match": {"status": "paid", "paid_at": {"$gte": week_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
        ]).to_list(1)
        week_installments_paid = week_installments_result[0]["total"] if week_installments_result else 0.0

        # Remboursements traités cette semaine
        week_refunds_pipeline = [
            {"$match": {"status": "processed", "updated_at": {"$gte": week_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        week_refunds_result = await db.refunds.aggregate(week_refunds_pipeline).to_list(1)
        week_processed_refunds = week_refunds_result[0]["total"] if week_refunds_result else 0.0

        # Revenu net cette semaine
        total_revenue_week = week_gross_revenue + week_installments_paid - week_processed_refunds

        # Revenus ce mois (brut pour commandes payées complètes, excluant les versements)
        month_revenue_pipeline = [
            {"$match": {
                "payment_status": PaymentStatus.effectue.value,
                "created_at": {"$gte": month_ago}
                # "$or": [
                #     {"payment_type": {"$ne": PaymentType.INSTALLMENTS.value}},
                #     {"payment_type": {"$exists": False}}
                # ]
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]
        month_revenue_result = await self.orders_collection.aggregate(month_revenue_pipeline).to_list(1)
        month_gross_revenue = month_revenue_result[0]["total"] if month_revenue_result else 0.0

        # Paid installments this month
        month_installments_result = await self.payment_installments_collection.aggregate([
            {"$match": {"status": "paid", "paid_at": {"$gte": month_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
        ]).to_list(1)
        month_installments_paid = month_installments_result[0]["total"] if month_installments_result else 0.0

        # Remboursements traités ce mois
        month_refunds_pipeline = [
            {"$match": {"status": "processed", "updated_at": {"$gte": month_ago}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        month_refunds_result = await db.refunds.aggregate(month_refunds_pipeline).to_list(1)
        month_processed_refunds = month_refunds_result[0]["total"] if month_refunds_result else 0.0

        # Revenu net ce mois
        total_revenue_month = month_gross_revenue + month_installments_paid - month_processed_refunds

        # 10. Commandes non achevées (toutes les commandes)
        pending_cursor = self.orders_collection.find({"status": {"$nin": [OrderStatus.livree.value, OrderStatus.annulee.value]}}).sort("created_at", -1)
        pending_orders = []
        async for order in pending_cursor:
            try:
                user = await self.users_collection.find_one({"_id": ObjectId(order["user_id"])})
                user_name = user.get("full_name", "Utilisateur") if user else "Utilisateur"
                if user_name is None:
                    user_name = "Utilisateur"
            except:
                user_name = "Utilisateur"
            pending_orders.append(PendingOrder(
                order_id=str(order["_id"]),
                user_name=user_name,
                status=order["status"],
                created_at=order["created_at"],
                total=order.get("total", 0)
            ))

        return VendorDashboardResponse(
            total_revenue=total_revenue,
            total_orders=total_orders,
            total_products=total_products,
            top_products=top_products,
            recent_orders=recent_orders,
            orders_by_status=orders_by_status,
            average_order_value=average_order_value,
            pending_orders=pending_orders,
            total_orders_today=total_orders_today,
            total_orders_week=total_orders_week,
            total_revenue_today=total_revenue_today,
            total_revenue_week=total_revenue_week,
            total_orders_month=total_orders_month,
            total_revenue_month=total_revenue_month
        )

    async def get_client_dashboard(self, user_id: str) -> Dict:
        """Récupérer les données du dashboard client, incluant les mesures et photo du profil."""
        user = await self.users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise Exception("Utilisateur non trouvé")

        # Extraire les mesures, taille et photo
        measurements = user.get("measurements", None)
        size = user.get("size", None)
        photo = user.get("photo", [])

        # Construire la réponse simplifiée pour le client
        dashboard_data = {
            "measurements": measurements,
            "size": size,
            "photo": photo
        }
        return dashboard_data

dashboard_service_fixed = DashboardServiceFixed()
