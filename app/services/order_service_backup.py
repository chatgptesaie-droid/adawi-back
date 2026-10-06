from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from app.db.mongo import db
from app.models.order import OrderCreate, OrderInDB, OrderPublic, OrderItem, OrderStatus, PaymentStatus, StatusLog
from app.services.cart_service import cart_service
from pydantic import BaseModel
from app.services.email_service import send_status_email
from app.services.notification_service import notification_service

class Notification(BaseModel):
    id: Optional[str]
    user_id: str  # admin, vendeur, etc.
    type: str     # ex: 'nouvelle_commande', 'paiement'
    message: str
    order_id: Optional[str] = None
    created_at: datetime
    read: bool = False

class OrderService:
    def __init__(self):
        self.collection = db.orders

    async def create_order(self, user_id: str, order: OrderCreate) -> OrderPublic:
        now = datetime.utcnow()
        order_data = order.dict()
        order_data["user_id"] = user_id
        order_data["created_at"] = now
        order_data["updated_at"] = now
        # Initialiser l'historique des statuts
        order_data["status_history"] = [
            {"status": order_data["status"], "changed_at": now, "comment": "Commande créée"}
        ]
        result = await self.collection.insert_one(order_data)
        order_data["id"] = str(result.inserted_id)
        # Utiliser le nouveau système de notifications enrichies
        await notification_service.notify_order_created(order_data["id"])
        return OrderPublic(**order_data)

    async def get_order(self, order_id: str, user_id: Optional[str] = None) -> Optional[OrderPublic]:
        query = {"_id": ObjectId(order_id)}
        if user_id:
            query["user_id"] = user_id
        order = await self.collection.find_one(query)
        if not order:
            return None
        order["id"] = str(order["_id"])
        
        # Enrichir les items avec toutes les images des produits
        for item in order.get("items", []):
            product = await db.products.find_one({"_id": ObjectId(item["product_id"])}, {"images": 1})
            if product and "images" in product and product["images"]:
                item["images"] = product["images"]  # Toutes les images
            else:
                item["images"] = []
        
        return OrderPublic(**order)

    async def get_orders(self, user_id: str) -> List[OrderPublic]:
        cursor = self.collection.find({"user_id": user_id}).sort("created_at", -1)
        orders = []
        async for order in cursor:
            order["id"] = str(order["_id"])
            # Enrichir les items avec toutes les images des produits
            for item in order.get("items", []):
                product = await db.products.find_one({"_id": ObjectId(item["product_id"])}, {"images": 1})
                if product and "images" in product and product["images"]:
                    item["images"] = product["images"]  # Toutes les images
                else:
                    item["images"] = []
            orders.append(OrderPublic(**order))
        return orders

    async def get_orders_advanced(self, current_user, status=None, payment_status=None, date_min=None, date_max=None):
        from datetime import datetime
        filter_query = {}
        # Admin : toutes les commandes
        # Vendeur : toutes les commandes (option : seulement celles contenant ses produits)
        # Client : seulement ses commandes
        if current_user.role == "client":
            filter_query["user_id"] = current_user.id
        # Pour admin et vendeur, on ne filtre pas sur user_id
        if status:
            filter_query["status"] = status
        if payment_status:
            filter_query["payment_status"] = payment_status
        if date_min or date_max:
            date_filter = {}
            if date_min:
                date_filter["$gte"] = datetime.fromisoformat(date_min)
            if date_max:
                date_filter["$lte"] = datetime.fromisoformat(date_max)
            filter_query["created_at"] = date_filter
        cursor = self.collection.find(filter_query).sort("created_at", -1)
        orders = []
        async for order in cursor:
            order["id"] = str(order["_id"])
            orders.append(OrderPublic(**order))
        return orders

    async def update_status(self, order_id: str, status: str, comment: Optional[str] = None, user_id: Optional[str] = None) -> Optional[OrderPublic]:
        query = {"_id": ObjectId(order_id)}
        if user_id:
            query["user_id"] = user_id
        now = datetime.utcnow()
        # Ajouter au log d'historique
        order = await self.collection.find_one(query)
        if not order:
            return None

        old_status = order.get("status")
        status_history = order.get("status_history", [])
        status_history.append({"status": status, "changed_at": now, "comment": comment})

        result = await self.collection.update_one(query, {"$set": {"status": status, "updated_at": now, "status_history": status_history}})
        if result.modified_count:
            # Gestion du stock selon le changement de statut
            if status == OrderStatus.annulee.value and old_status != OrderStatus.annulee.value:
                # Remettre le stock si la commande est annulée
                for item in order.get("items", []):
                    await db.products.update_one(
                        {"_id": ObjectId(item["product_id"])},
                        {"$inc": {"stock": item["quantity"]}}
                    )
            elif status == OrderStatus.en_preparation.value and old_status == OrderStatus.en_cours.value:
                # Décrémenter le stock quand on passe en préparation
                for item in order.get("items", []):
                    await db.products.update_one(
                        {"_id": ObjectId(item["product_id"])},
                        {"$inc": {"stock": -item["quantity"]}}
                    )

            # Envoi d'email au client (à garder)
            user = await db.users.find_one({"_id": ObjectId(order["user_id"])} )
            if user and user.get("email"):
                subject = f"Mise à jour de votre commande {order_id}"
                body = f"Bonjour {user.get('full_name', '')},\n\nLe statut de votre commande a changé : {status}.\n\nCommentaire : {comment or ''}"
                await send_status_email(user["email"], subject, body)
            # Notification staff (cloche commune)
            await notification_service.create_notification(
                user_id="staff",
                type="statut",
                message=f"Statut de la commande {order_id} changé en {status}",
                order_id=order_id
            )
            # Notification client (cloche)
            await notification_service.create_notification(
                user_id=order["user_id"],
                type="statut",
                message=f"Le statut de votre commande {order_id} a changé : {status}.",
                order_id=order_id
            )
            return await self.get_order(order_id, user_id)
        return None

    async def pay_order(self, order_id: str, success: bool, user_id: Optional[str] = None, payment_method: Optional[str] = None) -> Optional[OrderPublic]:
        query = {"_id": ObjectId(order_id)}
        if user_id:
            query["user_id"] = user_id
        now = datetime.utcnow()
        order = await self.collection.find_one(query)
        if not order:
            return None
        # Vérification stricte du stock avant paiement accepté
        if success:
            for item in order["items"]:
                product = await db.products.find_one({"_id": ObjectId(item["product_id"])})
                if not product or product.get("stock", 0) < item["quantity"]:
                    # Paiement refusé pour stock insuffisant
                    # Notification client
                    await notification_service.create_notification(
                        user_id=order["user_id"],
                        type="paiement",
                        message=f"Paiement refusé pour la commande {order_id} : stock insuffisant pour {item['product_id']}",
                        order_id=order_id
                    )
                    # Notification staff
                    await notification_service.create_notification(
                        user_id="staff",
                        type="paiement",
                        message=f"Paiement refusé pour la commande {order_id} : stock insuffisant pour {item['product_id']}",
                        order_id=order_id
                    )
                    # Email client
                    user = await db.users.find_one({"_id": ObjectId(order["user_id"])} )
                    if user and user.get("email"):
                        subject = f"Paiement refusé pour votre commande {order_id}"
                        body = f"Bonjour {user.get('full_name', '')},\n\nLe paiement de votre commande a été refusé : stock insuffisant pour un ou plusieurs produits."
                        await send_status_email(user["email"], subject, body)
                    return None
        payment_status = PaymentStatus.effectue.value if success else PaymentStatus.refuse.value
        comment = "Paiement accepté" if success else "Paiement refusé"
        status_history = order.get("status_history", [])
        status_history.append({"status": order.get("status", OrderStatus.en_cours.value), "changed_at": now, "comment": comment})
        update_fields = {
            "payment_status": payment_status,
            "updated_at": now,
            "status_history": status_history
        }
        # Ajouter la méthode de paiement si fournie
        if payment_method:
            update_fields["payment_method"] = payment_method
        # Si paiement refusé, passer la commande en statut 'annulee'
        if not success:
            update_fields["status"] = OrderStatus.annulee.value
        result = await self.collection.update_one(query, {"$set": update_fields})
        if result.modified_count:
            if success:
                for item in order["items"]:
                    await db.products.update_one(
                        {"_id": ObjectId(item["product_id"])},
                        {"$inc": {"stock": -item["quantity"]}}
                    )
            # Envoi d'email au client (à garder)
            user = await db.users.find_one({"_id": ObjectId(order["user_id"])} )
            if user and user.get("email"):
                if success:
                    subject = f"Paiement de votre commande {order_id}"
                    body = f"Bonjour {user.get('full_name', '')},\n\nLe paiement de votre commande a été accepté."
                else:
                    subject = f"Paiement refusé et commande annulée {order_id}"
                    body = f"Bonjour {user.get('full_name', '')},\n\nLe paiement de votre commande a été refusé et la commande a été annulée."
                await send_status_email(user["email"], subject, body)
            # Notification staff (cloche commune)
            await notification_service.create_notification(
                user_id="staff",
                type="paiement",
                message=f"Paiement {'accepté' if success else 'refusé'} pour la commande {order_id}",
                order_id=order_id
            )
            # Notification client (cloche)
            await notification_service.create_notification(
                user_id=order["user_id"],
                type="paiement",
                message=f"Votre paiement pour la commande {order_id} a été {'accepté' if success else 'refusé'}.",
                order_id=order_id
            )
            # Si paiement refusé, notifier annulation
            if not success:
                await notification_service.create_notification(
                    user_id=order["user_id"],
                    type="statut",
                    message=f"Votre commande {order_id} a été annulée suite à un paiement refusé.",
                    order_id=order_id
                )
                await notification_service.create_notification(
                    user_id="staff",
                    type="statut",
                    message=f"Commande {order_id} annulée suite à un paiement refusé.",
                    order_id=order_id
                )
            return await self.get_order(order_id, user_id)
        return None

order_service = OrderService() 