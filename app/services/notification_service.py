from app.db.mongo import db
from datetime import datetime
from bson import ObjectId
from app.models.notification import Notification
from app.services.websocket_service import push_notification_live
import asyncio

class NotificationService:
    def __init__(self):
        self.collection = db.notifications

    async def create_notification(self, user_id, type, message, order_id=None, product_id=None, ticket_id=None, refund_id=None, appointment_id=None, title=None):
        notif = {
            "user_id": user_id,
            "type": type,
            "message": message,
            "order_id": order_id,
            "product_id": product_id,
            "ticket_id": ticket_id,
            "refund_id": refund_id,
            "appointment_id": appointment_id,
            "title": title,
            "created_at": datetime.utcnow(),
            "read": False
        }

        # Enrichir avec les détails selon le type de notification
        if type in ["order_created", "order_paid", "order_shipped", "order_delivered", "order_cancelled"] and order_id:
            await self._enrich_order_details(notif, order_id)
        elif type in ["low_stock", "out_of_stock"] and product_id:
            await self._enrich_product_details(notif, product_id)
        elif type in ["new_ticket", "ticket_updated", "ticket_resolved"] and ticket_id:
            await self._enrich_ticket_details(notif, ticket_id)
        elif type in ["refund_requested", "refund_approved", "refund_rejected"] and refund_id:
            await self._enrich_refund_details(notif, refund_id)

        result = await self.collection.insert_one(notif)
        notif["id"] = str(result.inserted_id)
        # Envoi live via WebSocket (non bloquant)
        asyncio.create_task(push_notification_live(user_id, notif))
        return notif

    async def _enrich_order_details(self, notif, order_id):
        """Enrichir la notification avec les détails de la commande"""
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if order:
            # Récupérer les informations du client
            user = await db.users.find_one({"_id": ObjectId(order["user_id"])})
            customer_name = user.get("full_name", "Client") if user else "Client"
            customer_email = user.get("email", "") if user else ""

            # Récupérer les détails des produits avec images
            order_items = []
            for item in order.get("items", []):
                product = await db.products.find_one({"_id": ObjectId(item["product_id"])})
                if product:
                    order_items.append({
                        "product_id": str(product["_id"]),
                        "product_name": product.get("name", "Produit"),
                        "quantity": item.get("quantity", 1),
                        "price": item.get("price", 0),
                        "size": item.get("size", ""),
                        "color": item.get("color", ""),
                        "images": product.get("images", []),
                        "sku": product.get("sku", "")
                    })

            notif["order_details"] = {
                "customer_name": customer_name,
                "customer_email": customer_email,
                "total_amount": order.get("total", 0),
                "status": order.get("status", "pending"),
                "payment_status": order.get("payment_status", "pending"),
                "payment_method": order.get("payment_method", ""),
                "delivery_method": order.get("delivery_method", ""),
                "items_count": len(order.get("items", [])),
                "items": order_items,
                "created_at": order.get("created_at"),
                "updated_at": order.get("updated_at")
            }

    async def _enrich_product_details(self, notif, product_id):
        """Enrichir la notification avec les détails du produit"""
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if product:
            # Récupérer les informations du vendeur
            seller = await db.users.find_one({"_id": ObjectId(product.get("seller_id"))})
            seller_name = seller.get("full_name", "Vendeur") if seller else "Vendeur"

            notif["product_details"] = {
                "product_id": str(product["_id"]),
                "product_name": product.get("name", "Produit"),
                "sku": product.get("sku", ""),
                "current_stock": product.get("stock", 0),
                "min_stock_threshold": product.get("min_stock_threshold", 5),
                "price": product.get("price", 0),
                "images": product.get("images", []),
                "seller_name": seller_name,
                "category": product.get("category", ""),
                "description": product.get("description", "")
            }

    async def _enrich_ticket_details(self, notif, ticket_id):
        """Enrichir la notification avec les détails du ticket"""
        ticket = await db.tickets.find_one({"_id": ObjectId(ticket_id)})
        if ticket:
            # Récupérer les informations du client
            user = await db.users.find_one({"_id": ObjectId(ticket.get("user_id"))})
            customer_name = user.get("full_name", "Client") if user else "Client"

            notif["ticket_details"] = {
                "ticket_id": str(ticket["_id"]),
                "subject": ticket.get("subject", ""),
                "description": ticket.get("description", ""),
                "status": ticket.get("status", "open"),
                "priority": ticket.get("priority", "normal"),
                "customer_name": customer_name,
                "customer_email": ticket.get("customer_email", ""),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
                "assigned_to": ticket.get("assigned_to", ""),
                "category": ticket.get("category", "")
            }

    async def _enrich_refund_details(self, notif, refund_id):
        """Enrichir la notification avec les détails de la demande de remboursement"""
        refund = await db.refunds.find_one({"_id": ObjectId(refund_id)})
        if refund:
            # Récupérer les informations de la commande
            order = await db.orders.find_one({"_id": ObjectId(refund.get("order_id"))})
            order_total = order.get("total", 0) if order else 0

            # Récupérer les informations du client
            user = await db.users.find_one({"_id": ObjectId(refund.get("user_id"))})
            customer_name = user.get("full_name", "Client") if user else "Client"

            notif["refund_details"] = {
                "refund_id": str(refund["_id"]),
                "order_id": str(refund.get("order_id", "")),
                "customer_name": customer_name,
                "amount": refund.get("amount", 0),
                "reason": refund.get("reason", ""),
                "status": refund.get("status", "pending"),
                "description": refund.get("description", ""),
                "order_total": order_total,
                "created_at": refund.get("created_at"),
                "updated_at": refund.get("updated_at")
            }

    async def get_notifications(self, user_id):
        cursor = self.collection.find({"user_id": user_id, "read": False}).sort("created_at", -1)
        notifs = []
        async for n in cursor:
            n["id"] = str(n["_id"])
            notifs.append(Notification(**n))
        return notifs

    async def mark_as_read(self, notif_id):
        await self.collection.update_one({"_id": ObjectId(notif_id)}, {"$set": {"read": True}})

    async def get_notification_details(self, notif_id, user_id):
        """Récupérer les détails d'une notification et la marquer automatiquement comme lue"""
        # Récupérer la notification
        notif = await self.collection.find_one({"_id": ObjectId(notif_id), "user_id": user_id})
        if not notif:
            return None

        # Marquer automatiquement comme lue
        await self.mark_as_read(notif_id)

        # Convertir en objet Notification avec tous les détails
        notif["id"] = str(notif["_id"])
        notification = Notification(**notif)

        return notification

    # Méthodes de convenance pour différents types de notifications

    async def notify_order_created(self, order_id: str):
        """Notifier la création d'une commande"""
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if order:
            # Notification admin/staff
            await self.create_notification(
                user_id="staff",
                type="order_created",
                message=f"Nouvelle commande #{order_id} créée",
                order_id=order_id
            )

            # Notification client
            await self.create_notification(
                user_id=order["user_id"],
                type="order_created",
                message=f"Votre commande #{order_id} a été créée avec succès",
                order_id=order_id
            )

            # Notifications vendeurs concernés
            product_ids = [item["product_id"] for item in order.get("items", [])]
            sellers = set()
            for pid in product_ids:
                product = await db.products.find_one({"_id": ObjectId(pid)})
                if product and product.get("seller_id"):
                    sellers.add(product["seller_id"])

            for seller_id in sellers:
                await self.create_notification(
                    user_id=seller_id,
                    type="order_created",
                    message=f"Nouvelle commande #{order_id} contient vos produits",
                    order_id=order_id
                )

    async def notify_low_stock(self, product_id: str):
        """Notifier un stock faible"""
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if product:
            stock = product.get("stock", 0)
            threshold = product.get("min_stock_threshold", 5)

            # Notification vendeur si stock <= seuil minimum
            if product.get("seller_id") and stock <= threshold:
                await self.create_notification(
                    user_id=product["seller_id"],
                    type="low_stock",
                    message=f"Stock faible pour {product.get('name', 'Produit')} : {stock} unités restantes (seuil: {threshold})",
                    product_id=product_id
                )

            # Notification admin si stock très critique (seuil minimum / 2)
            critical_threshold = max(1, threshold // 2)
            if stock <= critical_threshold:
                await self.create_notification(
                    user_id="staff",
                    type="low_stock",
                    message=f"ALERTE STOCK CRITIQUE : {product.get('name', 'Produit')} - {stock} unités (seuil critique: {critical_threshold})",
                    product_id=product_id
                )

    async def notify_out_of_stock(self, product_id: str):
        """Notifier rupture de stock"""
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if product:
            # Notification vendeur
            if product.get("seller_id"):
                await self.create_notification(
                    user_id=product["seller_id"],
                    type="out_of_stock",
                    message=f"Rupture de stock pour {product.get('name', 'Produit')}",
                    product_id=product_id
                )

            # Notification admin
            await self.create_notification(
                user_id="staff",
                type="out_of_stock",
                message=f"Rupture de stock : {product.get('name', 'Produit')}",
                product_id=product_id
            )

    async def notify_new_ticket(self, ticket_id: str):
        """Notifier un nouveau ticket"""
        ticket = await db.tickets.find_one({"_id": ObjectId(ticket_id)})
        if ticket:
            # Notification admin/staff
            await self.create_notification(
                user_id="staff",
                type="new_ticket",
                message=f"Nouveau ticket : {ticket.get('subject', 'Sans sujet')}",
                ticket_id=ticket_id
            )

            # Notification client
            await self.create_notification(
                user_id=ticket["user_id"],
                type="new_ticket",
                message=f"Votre ticket #{ticket_id} a été créé",
                ticket_id=ticket_id
            )

    async def notify_refund_requested(self, user_id: str, refund_id: str, reason: str, amount: float):
        """Notifier une demande de remboursement"""
        # Notification admin/staff
        await self.create_notification(
            user_id="staff",
            type="refund_requested",
            message=f"Nouvelle demande de remboursement (raison: {reason}) : {amount}XOF - ID: {refund_id}",
            refund_id=refund_id
        )

        # Notification client
        await self.create_notification(
            user_id=user_id,
            type="refund_requested",
            message=f"Votre demande de remboursement #{refund_id} (raison: {reason}, montant: {amount}XOF) a été soumise",
            refund_id=refund_id
        )

    async def notify_refund_status_changed(self, refund_id: str, new_status: str):
        """Notifier un changement de statut de remboursement"""
        refund = await db.refunds.find_one({"_id": ObjectId(refund_id)})
        if refund:
            status_messages = {
                "approved": "approuvée",
                "rejected": "rejetée",
                "processed": "traitée"
            }

            status_text = status_messages.get(new_status, new_status)

            # Notification client
            await self.create_notification(
                user_id=refund["user_id"],
                type=f"refund_{new_status}",
                message=f"Votre demande de remboursement #{refund_id} a été {status_text}",
                refund_id=refund_id
            )

            # Notification admin si nécessaire
            if new_status in ["approved", "rejected"]:
                await self.create_notification(
                    user_id="staff",
                    type=f"refund_{new_status}",
                    message=f"Demande de remboursement #{refund_id} {status_text}",
                    refund_id=refund_id
                )

    async def notify_new_appointment(self, appointment_id: str):
        """Notifier un nouveau rendez-vous aux vendeurs et admins"""
        appointment = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
        if not appointment:
            return

        # Créer une notification pour le staff (admin/vendeurs)
        message = f"Nouveau rendez-vous : {appointment.get('title', 'Sans titre')} - {appointment.get('client_name', 'Client')} le {appointment.get('appointment_date', '').strftime('%d/%m/%Y %H:%M') if appointment.get('appointment_date') else 'Date inconnue'}"

        await self.create_notification(
            user_id="staff",
            type="appointment",
            message=message,
            appointment_id=appointment_id,
            title="Nouveau rendez-vous"
        )

notification_service = NotificationService()
