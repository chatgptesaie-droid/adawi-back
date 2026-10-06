from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from app.db.mongo import db
from app.models.order import OrderCreate, OrderInDB, OrderPublic, OrderItem, OrderStatus, PaymentStatus, StatusLog, PaymentType
from app.models.payment_installment import InstallmentPlanCreate, PaymentMethod
from app.services.cart_service import cart_service
from app.services.payment_installment_service import payment_installment_service
from app.services.product_service import product_service
from pydantic import BaseModel
from app.services.email_service import send_status_email
from app.services.notification_service import notification_service
from app.services.sms_service import (
    customer_name,
    customer_phone,
    order_status_message,
    send_customer_sms,
    short_reference,
    status_label,
)
import logging

logger = logging.getLogger(__name__)

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

    async def create_order(self, user_id: str, order: BaseModel) -> OrderPublic:
        import logging
        from bson import json_util
        from datetime import datetime, time, date
        now = datetime.utcnow()
        try:
            order_data = order.dict()
            logging.info(f"Creating order with data: {order_data}")
            order_data["user_id"] = user_id
            order_data["created_at"] = now
            order_data["updated_at"] = now
            # Convert datetime.date fields to datetime.datetime for MongoDB compatibility
            if "delivery_date" in order_data and isinstance(order_data["delivery_date"], str):
                # If delivery_date is string, parse to datetime
                order_data["delivery_date"] = datetime.fromisoformat(order_data["delivery_date"])
            elif "delivery_date" in order_data and isinstance(order_data["delivery_date"], date):
                # Convert date to datetime at midnight
                order_data["delivery_date"] = datetime.combine(order_data["delivery_date"], time.min)
            # Initialiser l'historique des statuts
            order_data["status_history"] = [
                {"status": order_data["status"], "changed_at": now, "comment": "Commande créée"}
            ]
            # Convertir les objets non sérialisables en JSON compatible BSON
            order_data_json = json_util.loads(json_util.dumps(order_data))
            result = await self.collection.insert_one(order_data_json)
            order_data["id"] = str(result.inserted_id)
            # Désactiver les notifications pour les ventes physiques en boutique.
            is_physical_sale = (
                order_data.get("status") in (OrderStatus.boutique.value, OrderStatus.livree.value) and
                order_data.get("payment_method") == "boutique"
            )
            if not is_physical_sale:
                # Utiliser le nouveau système de notifications enrichies
                await notification_service.notify_order_created(order_data["id"])
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            initial_status = status_label(order_data["status"])
            await send_customer_sms(
                customer_phone(user, order_data),
                customer_name(user, order_data.get("customer_name") or "Client"),
                f"Votre commande {short_reference(order_data['id'])} a été enregistrée. Statut : {initial_status}.",
                occurred_at=now,
                event="order.created",
            )
            return OrderPublic(**order_data)
        except Exception as e:
            logging.error(f"Error creating order: {e}")
            raise

    async def get_order(self, order_id: str, user_id: Optional[str] = None) -> Optional[OrderPublic]:
        try:
            query = {"_id": ObjectId(order_id)}
        except Exception:
            return None  # Invalid ObjectId

        if user_id:
            query["user_id"] = user_id
        order = await self.collection.find_one(query)
        if not order:
            return None
        order["id"] = str(order["_id"])

        # Enrichir les items avec les informations complètes des produits
        items = order.get("items", [])
        if not isinstance(items, list):
            items = []
        for item in items:
            try:
                product_id = item.get("product_id")
                if product_id:
                    product = await db.products.find_one({"_id": ObjectId(product_id)}, {"name": 1, "description": 1, "price": 1, "images": 1, "category": 1})
                    if product:
                        item["product_name"] = product.get("name", "")
                        item["product_description"] = product.get("description", "")
                        item["product_price"] = product.get("price", 0.0)
                        item["product_category"] = product.get("category", "")
                        item["images"] = product.get("images", [])  # Toutes les images
                        item["product_id"] = product_id  # Garder l'ID du produit
                    else:
                        item["product_name"] = ""
                        item["product_description"] = ""
                        item["product_price"] = 0.0
                        item["product_category"] = ""
                        item["images"] = []
                else:
                    item["product_name"] = ""
                    item["product_description"] = ""
                    item["product_price"] = 0.0
                    item["product_category"] = ""
                    item["images"] = []
            except Exception:
                # Handle any error in product lookup
                item["product_name"] = ""
                item["product_description"] = ""
                item["product_price"] = 0.0
                item["product_category"] = ""
                item["images"] = []

        return OrderPublic(**order)

    async def get_orders(self, user_id: str) -> List[OrderPublic]:
        # 1. Chercher TOUTES les commandes de l'utilisateur
        # "user_id": user_id → filtre les commandes de cet utilisateur
        # sort("created_at", -1) → trie de la plus récente à la plus ancienne
        cursor = self.collection.find({"user_id": user_id}).sort("created_at", -1)
        orders = []
        # 2. Traiter UNE SEULE commande à la fois (grâce à async for)
        async for order in cursor:
            # 3. Transformer _id MongoDB (ObjectId) en string pour l'API
            order["id"] = str(order["_id"])
            # 4. Pour CHAQUE article dans la commande...
            for item in order.get("items", []):
                # 5. Chercher le produit correspondant en DB
                product = await db.products.find_one({"_id": ObjectId(item["product_id"])}, # Quel produit ?    
                                                    {"images": 1}) # Quelles images ?
                # 6. Ajouter les images à l'article (ou [] si pas d'images)
                if product and "images" in product and product["images"]:
                    item["images"] = product["images"]  # Toutes les images
                else:
                    item["images"] = []
            try:
                # 7. Ignorer les commandes invalides (sans date)
                # Gérer les commandes avec des champs manquants
                if "created_at" not in order:
                    continue
                if "updated_at" not in order:
                    continue
                # 8. Ajouter la commande complète (avec images enrichies) à la liste    
                # 8. Ajouter la commande à la liste finale
                orders.append(OrderPublic(**order)) # 9. Convertir en OrderPublic (schéma API)  
            except Exception as e:
                # Ne pas lever l'exception, continuer avec les autres commandes
                continue
        # 10. Retourner la liste complète des commandes 
        return orders
    # ___________________________________________________________
    async def get_orders_advanced(self, current_user, status=None, payment_status=None, date_min=None, date_max=None):
        from datetime import datetime
        filter_query = {}

        # Admin : toutes les commandes
        # Vendeur : toutes les commandes (option : seulement celles contenant ses produits)

        # Admin et Vendeur : toutes les commandes (comme demandé)
        # Client : seulement ses commandes
        if current_user and hasattr(current_user, 'role') and current_user.role == "client":
            filter_query["user_id"] = current_user.id
        # Pour admin et vendeur, on ne filtre pas sur user_id (ils voient tout)


        # Pour admin et vendeur, on ne filtre pas sur user_id
        if status:
            filter_query["status"] = status
        if payment_status:
            filter_query["payment_status"] = payment_status
        if date_min or date_max:
            date_filter = {}
            if date_min:
                try:
                    date_filter["$gte"] = datetime.fromisoformat(date_min)
                except ValueError as e:
                    raise ValueError(f"Format de date invalide pour date_min: {date_min}")
            if date_max:
                try:
                    date_filter["$lte"] = datetime.fromisoformat(date_max)
                except ValueError as e:
                    raise ValueError(f"Format de date invalide pour date_max: {date_max}")
            filter_query["created_at"] = date_filter

        cursor = self.collection.find(filter_query).sort("created_at", -1)
        orders = []
        async for order in cursor:
            order["id"] = str(order["_id"])
            # Enrichir les items avec toutes les images des produits
            items = order.get("items", [])
            if not isinstance(items, list):
                items = []
            for item in items:
                try:
                    product_id = item.get("product_id")
                    if product_id:
                        product = await db.products.find_one({"_id": ObjectId(product_id)}, {"images": 1})
                        if product and "images" in product and product["images"]:
                            item["images"] = product["images"]  # Toutes les images
                        else:
                            item["images"] = []
                    else:
                        item["images"] = []
                except Exception:
                    item["images"] = []
            try:
                # Gérer les commandes avec des champs manquants
                if "created_at" not in order:
                    continue
                if "updated_at" not in order:
                    continue
                orders.append(OrderPublic(**order))
            except Exception as e:
                # Ne pas lever l'exception, continuer avec les autres commandes
                continue

        return orders
    # ___________________________________________________________
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
            elif status in [OrderStatus.en_preparation.value, OrderStatus.boutique.value, OrderStatus.livree.value] and old_status == OrderStatus.en_cours.value:
                # Une commande sort du stock au démarrage du traitement ou à la vente directe.
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
            await send_customer_sms(
                customer_phone(user, order),
                customer_name(user),
                order_status_message(status, order_id),
                occurred_at=now,
                event="order.status_changed",
            )
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
    # ___________________________________________________________   
    async def pay_order(
        self,
        order_id: str,
        success: bool,
        user_id: Optional[str] = None,
        payment_method: Optional[str] = None,
        send_email: bool = True,
    ) -> Optional[OrderPublic]:
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"🔄 Début pay_order - order_id: {order_id}, success: {success}, payment_method: {payment_method}, user_id: {user_id}")

        query = {"_id": ObjectId(order_id)}
        if user_id:
            query["user_id"] = user_id
            logger.info(f"🔍 Query avec user_id: {query}")
        else:
            logger.info(f"🔍 Query sans user_id: {query}")

        now = datetime.utcnow()
        logger.info(f"🔍 Recherche commande avec query: {query}")
        order = await self.collection.find_one(query)
        if not order:
            logger.error(f"❌ Commande {order_id} non trouvée avec query: {query}")
            # Essayer sans user_id pour diagnostiquer
            fallback_query = {"_id": ObjectId(order_id)}
            logger.info(f"🔍 Tentative fallback sans user_id: {fallback_query}")
            fallback_order = await self.collection.find_one(fallback_query)
            if fallback_order:
                logger.error(f"❌ Commande trouvée sans user_id, mais user_id mismatch. Commande user_id: {fallback_order.get('user_id')}, fourni: {user_id}")
                logger.info(f"📋 Détails commande fallback: status={fallback_order.get('status')}, payment_status={fallback_order.get('payment_status')}")
            else:
                logger.error(f"❌ Commande vraiment introuvable")
            return None

        logger.info(f"📋 Commande trouvée: {order_id}, statut actuel: {order.get('status')}, payment_status: {order.get('payment_status')}, user_id commande: {order.get('user_id')}")
        logger.info(f"📋 Champs commande: {list(order.keys())}")
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
                    # Email client (ne pas bloquer si ça échoue)
                    user = await db.users.find_one({"_id": ObjectId(order["user_id"])} )
                    if user and user.get("email"):
                        try:
                            subject = f"Paiement refusé pour votre commande {order_id}"
                            body = f"Bonjour {user.get('full_name', '')},\n\nLe paiement de votre commande a été refusé : stock insuffisant pour un ou plusieurs produits."
                            await send_status_email(user["email"], subject, body)
                            logger.info(f"✅ Email de refus de paiement envoyé à {user.get('email')}")
                        except Exception as e:
                            logger.error(f"❌ Erreur envoi email de refus de paiement: {e}")
                            logger.warning("⚠️ Refus de paiement réussi malgré l'erreur email")
                    await send_customer_sms(
                        customer_phone(user, order),
                        customer_name(user),
                        f"Le paiement de votre commande {short_reference(order_id)} a échoué : stock insuffisant.",
                        occurred_at=now,
                        event="payment.failed.insufficient_stock",
                    )
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
    #    # Si paiement accepté, passer la commande en statut 'en_preparation'
    #     elif success:
    #         update_fields["status"] = OrderStatus.en_preparation.value 
        logger.info(f"🔄 Mise à jour commande {order_id} avec champs: {update_fields}")
        result = await self.collection.update_one(query, {"$set": update_fields})
        logger.info(f"📊 Résultat update_one: matched_count={result.matched_count}, modified_count={result.modified_count}")

        if result.modified_count:
            logger.info(f"✅ Commande {order_id} mise à jour avec succès")
            # Stock décrémenté seulement lors du passage en préparation, pas au paiement
            # if success:
            #     for item in order["items"]:
            #         await db.products.update_one(
            #             {"_id": ObjectId(item["product_id"])},
            #             {"$inc": {"stock": -item["quantity"]}}
            #         )
            # Envoi d'email au client (ne pas bloquer si ça échoue)
            try:
                user = await db.users.find_one({"_id": ObjectId(order["user_id"])} )
                if send_email and user and user.get("email"):
                    if success:
                        subject = f"Paiement de votre commande {order_id}"
                        body = f"Bonjour {user.get('full_name', '')},\n\nLe paiement de votre commande a été accepté."
                    else:
                        subject = f"Paiement refusé et commande annulée {order_id}"
                        body = f"Bonjour {user.get('full_name', '')},\n\nLe paiement de votre commande a été refusé et la commande a été annulée."
                    await send_status_email(user["email"], subject, body)
                    logger.info(f"✅ Email envoyé pour commande {order_id}")
                await send_customer_sms(
                    customer_phone(user, order),
                    customer_name(user),
                    f"Le paiement de votre commande {short_reference(order_id)} {'a été effectué' if success else 'a échoué'}.",
                    occurred_at=now,
                    event="payment.completed" if success else "payment.failed",
                )
            except Exception as e:
                logger.error(f"❌ Erreur envoi email pour commande {order_id}: {e}")
                logger.warning("⚠️ Mise à jour commande réussie malgré l'erreur email")
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
            updated_order = await self.get_order(order_id, user_id)
            logger.info(f"📋 Commande mise à jour récupérée: payment_status={updated_order.payment_status if updated_order else 'None'}")
            return updated_order
        else:
            logger.error(f"❌ Échec mise à jour commande {order_id} - modified_count=0")
            return None
    # ___________________________________________________________
    # === MÉTHODES POUR PAIEMENTS EN VERSEMENTS ===

    async def create_installment_order(
        self,
        user_id: str,
        order_data: dict,
        installment_plan: InstallmentPlanCreate,
        created_by: str
    ) -> OrderPublic:
        """
        Crée une commande avec paiement en versements
        """
        now = datetime.utcnow()

        # Calculer le total des versements
        total_installments = installment_plan.first_payment_amount + (installment_plan.installment_amount * (installment_plan.installments_count - 1))

        # Vérifier que le total correspond au montant de la commande
        if abs(total_installments - order_data["total"]) > 0.01:
            raise ValueError(f"Le total des versements ({total_installments}) ne correspond pas au montant de la commande ({order_data['total']})")

        delivered_at_creation = order_data.get("status") == OrderStatus.livree.value
        if delivered_at_creation:
            for item in order_data.get("items", []):
                product = await db.products.find_one({"_id": ObjectId(item["product_id"])})
                if not product or product.get("stock", 0) < item["quantity"]:
                    available_stock = product.get("stock", 0) if product else 0
                    raise ValueError(
                        f"Stock insuffisant pour le produit {item['product_id']}. "
                        f"Stock disponible: {available_stock}"
                    )

        # Créer la commande avec les champs de versements
        order_dict = {
            **order_data,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "payment_type": PaymentType.INSTALLMENTS,
            "installments_count": installment_plan.installments_count,
            "customer_name": installment_plan.customer_name,
            "customer_phone": installment_plan.customer_phone,
            "paid_amount": 0.0,
            "remaining_amount": order_data["total"],
            "installments": [],
            "payment_status": PaymentStatus.en_cours,
            "status_history": [
                {"status": order_data["status"], "changed_at": now, "comment": "Commande créée avec paiement en versements"}
            ]
        }

        # Insérer la commande
        result = await self.collection.insert_one(order_dict)
        order_id = str(result.inserted_id)

        # Créer le plan de versements
        installment_ids = await payment_installment_service.create_installment_plan(
            order_id=order_id,
            plan_data=installment_plan,
            created_by=created_by
        )

        # Mettre à jour la commande avec les IDs des versements
        await self.collection.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"installments": installment_ids}}
        )

        # Le premier versement est déjà marqué comme payé dans le service de versements
        # Nous devons juste mettre à jour les montants de la commande
        if installment_ids:
            first_installment_id = installment_ids[0]
            logger.info(f"Mise à jour des montants de commande pour le premier versement payé: order_id={order_id}, installment_id={first_installment_id}, amount={installment_plan.first_payment_amount}")

            # Mettre à jour directement les montants de la commande
            new_paid_amount = installment_plan.first_payment_amount
            new_remaining_amount = order_data["total"] - installment_plan.first_payment_amount

            update_data = {
                "paid_amount": new_paid_amount,
                "remaining_amount": new_remaining_amount,
                "updated_at": datetime.utcnow()
            }

            result = await self.collection.update_one(
                {"_id": ObjectId(order_id)},
                {"$set": update_data}
            )

            if result.modified_count:
                logger.info(f"Montants de commande mis à jour avec succès pour le premier versement: paid={new_paid_amount}, remaining={new_remaining_amount}")
            else:
                logger.error(f"Échec de la mise à jour des montants de commande pour le premier versement")



        logger.info(f"Commande en versements créée: {order_id} avec {len(installment_ids)} versements")
        return await self.get_order(order_id)
    # ___________________________________________________________
    # === MÉTHODES POUR LE PAIEMENT DES VERSEMENTS ===  
    async def pay_installment(
        self,
        order_id: str,
        installment_id: str,
        paid_amount: float,
        payment_method: PaymentMethod,
        paid_by: str
    ) -> bool:
        """
        Enregistre le paiement d'un versement et met à jour la commande
        """
        # Payer le versement
        success = await payment_installment_service.pay_installment(
            installment_id=installment_id,
            paid_amount=paid_amount,
            payment_method=payment_method,
            paid_by=paid_by
        )

        if not success:
            return False

        # Mettre à jour les montants de la commande
        order = await self.collection.find_one({"_id": ObjectId(order_id)})
        if not order:
            return False

        new_paid_amount = order.get("paid_amount", 0.0) + paid_amount
        new_remaining_amount = order.get("remaining_amount", 0.0) - paid_amount

        update_data = {
            "paid_amount": new_paid_amount,
            "remaining_amount": new_remaining_amount,
            "updated_at": datetime.utcnow()
        }

        # Vérifier si tous les versements sont payés
        installments = await payment_installment_service.get_installments_by_order(order_id)
        all_paid = all(inst.status == "paid" for inst in installments)

        if all_paid:
            update_data["payment_status"] = PaymentStatus.effectue
            if order.get("status") != OrderStatus.livree.value:
                update_data["status"] = OrderStatus.en_preparation

        result = await self.collection.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": update_data}
        )

        if result.modified_count:
            # Notifications
            await notification_service.create_notification(
                user_id="staff",
                type="paiement",
                message=f"Versement payé pour commande {order_id}: {paid_amount} FCFA",
                order_id=order_id
            )

            if all_paid:
                await notification_service.create_notification(
                    user_id=order["user_id"],
                    type="paiement",
                    message=f"Tous les versements de votre commande {order_id} ont été payés. Commande en préparation.",
                    order_id=order_id
                )

            logger.info(f"Versement payé pour commande {order_id}: {paid_amount} FCFA")
            return True

        return False
    # ___________________________________________________________
    # === MÉTHODES POUR LE RÉSUMÉ DES PAIEMENTS ===
    async def get_order_payment_summary(self, order_id: str) -> dict:
        """
        Récupère le résumé des paiements pour une commande
        """
        order = await self.collection.find_one({"_id": ObjectId(order_id)})
        if not order:
            return None

        installments = await payment_installment_service.get_installments_by_order(order_id)

        # Use the authoritative paid_amount and remaining_amount from the order document
        total_amount = order.get("total", 0.0)
        paid_amount = order.get("paid_amount", 0.0)
        remaining_amount = order.get("remaining_amount", 0.0)

        return {
            "order_id": order_id,
            "total_amount": total_amount,
            "paid_amount": paid_amount,
            "remaining_amount": remaining_amount,
            "payment_type": order.get("payment_type", "full"),
            "installments_count": len(installments),
            "installments": [inst.dict() for inst in installments]
        }



order_service = OrderService()
