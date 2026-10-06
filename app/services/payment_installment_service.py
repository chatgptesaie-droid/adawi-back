from typing import List, Optional
from datetime import datetime, timedelta
import re
from bson import ObjectId
from app.db.mongo import db
from app.models.payment_installment import (
    PaymentInstallment,
    PaymentInstallmentCreate,
    PaymentInstallmentUpdate,
    PaymentInstallmentPublic,
    InstallmentPlanCreate,
    InstallmentStatus,
    PaymentMethod
)
from app.models.order import OrderPublic, PaymentStatus
import logging

logger = logging.getLogger(__name__)

class PaymentInstallmentService:
    def __init__(self):
        self.collection = db.payment_installments

    async def create_installment_plan(
        self,
        order_id: str,
        plan_data: InstallmentPlanCreate,
        created_by: str
    ) -> List[str]:
        """
        Crée un plan de versements pour une commande
        """
        installment_ids = []

        # Calculer les montants des versements
        total_amount = plan_data.first_payment_amount + (plan_data.installment_amount * (plan_data.installments_count - 1))

        # Créer le premier versement (payé immédiatement)
        first_installment = PaymentInstallmentCreate(
            order_id=order_id,
            installment_number=1,
            amount=plan_data.first_payment_amount,
            due_date=plan_data.due_dates[0] if plan_data.due_dates else datetime.utcnow()
        )

        first_id = await self.create_installment(first_installment, created_by)
        installment_ids.append(first_id)

        # Marquer le premier versement comme payé
        await self.pay_installment(first_id, plan_data.first_payment_amount, PaymentMethod.CASH, created_by)

        # Créer les versements suivants
        for i in range(1, plan_data.installments_count):
            installment = PaymentInstallmentCreate(
                order_id=order_id,
                installment_number=i + 1,
                amount=plan_data.installment_amount,
                due_date=plan_data.due_dates[i] if i < len(plan_data.due_dates) else datetime.utcnow() + timedelta(days=30 * i)
            )

            installment_id = await self.create_installment(installment, created_by)
            installment_ids.append(installment_id)

        logger.info(f"Plan de versements créé pour commande {order_id}: {plan_data.installments_count} versements")
        return installment_ids

    async def create_installment(
        self,
        installment_data: PaymentInstallmentCreate,
        created_by: str
    ) -> str:
        """
        Crée un versement individuel
        """
        installment_dict = installment_data.dict()
        installment_dict["_id"] = ObjectId()
        installment_dict["created_by"] = created_by
        installment_dict["created_at"] = datetime.utcnow()
        installment_dict["updated_at"] = datetime.utcnow()

        result = await self.collection.insert_one(installment_dict)
        return str(result.inserted_id)

    async def get_installments_by_order(self, order_id: str) -> List[PaymentInstallmentPublic]:
        """
        Récupère tous les versements d'une commande
        """
        cursor = self.collection.find({"order_id": order_id}).sort("installment_number", 1)
        installments = []

        async for doc in cursor:
            # Convertir ObjectId en string
            doc["_id"] = str(doc["_id"])
            installments.append(PaymentInstallmentPublic(**doc))

        return installments

    async def get_installment_by_id(self, installment_id: str) -> Optional[PaymentInstallmentPublic]:
        """
        Récupère un versement par son ID
        """
        doc = await self.collection.find_one({"_id": ObjectId(installment_id)})
        if doc:
            # Convertir ObjectId en string
            doc["_id"] = str(doc["_id"])
            return PaymentInstallmentPublic(**doc)
        return None

    async def pay_installment(
        self,
        installment_id: str,
        paid_amount: float,
        payment_method: PaymentMethod,
        paid_by: str
    ) -> bool:
        """
        Enregistre le paiement d'un versement
        """
        # Vérifier que le versement existe et n'est pas déjà payé ou annulé
        installment = await self.collection.find_one({"_id": ObjectId(installment_id)})
        if not installment:
            logger.error(f"Versement {installment_id} non trouvé")
            raise ValueError("Versement non trouvé")
        if installment.get("status") == InstallmentStatus.PAID:
            logger.error(f"Versement {installment_id} déjà payé")
            raise ValueError("Versement déjà payé")
        if installment.get("status") == InstallmentStatus.CANCELLED:
            logger.error(f"Versement {installment_id} annulé, paiement impossible")
            raise ValueError("Versement annulé, paiement impossible")
        # Vérifier que le montant payé est correct
        if abs(paid_amount - installment.get("amount", 0)) > 0.01:
            logger.error(f"Montant payé {paid_amount} ne correspond pas au montant dû {installment.get('amount')}")
            raise ValueError("Montant payé incorrect")

        update_data = {
            "paid_amount": paid_amount,
            "payment_method": payment_method,
            "status": InstallmentStatus.PAID,
            "paid_at": datetime.utcnow(),
            "paid_by": paid_by,
            "updated_at": datetime.utcnow()
        }

        result = await self.collection.update_one(
            {"_id": ObjectId(installment_id)},
            {"$set": update_data}
        )

        if result.modified_count > 0:
            logger.info(f"Versement {installment_id} marqué comme payé: {paid_amount} FCFA")
            return True

        return False

    async def get_overdue_installments(self, days_overdue: int = 0) -> List[PaymentInstallmentPublic]:
        """
        Récupère les versements en retard
        """
        overdue_date = datetime.utcnow() - timedelta(days=days_overdue)

        cursor = self.collection.find({
            "due_date": {"$lt": overdue_date},
            "status": {"$in": [InstallmentStatus.PENDING, InstallmentStatus.OVERDUE]}
        }).sort("due_date", 1)

        installments = []
        async for doc in cursor:
            # Convertir ObjectId en string
            doc["_id"] = str(doc["_id"])
            installments.append(PaymentInstallmentPublic(**doc))

        return installments

    async def update_overdue_status(self) -> int:
        """
        Met à jour le statut des versements en retard
        """
        overdue_date = datetime.utcnow()

        result = await self.collection.update_many(
            {
                "due_date": {"$lt": overdue_date},
                "status": InstallmentStatus.PENDING
            },
            {
                "$set": {
                    "status": InstallmentStatus.OVERDUE,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        logger.info(f"{result.modified_count} versements marqués comme en retard")
        return result.modified_count

    async def cancel_installment(self, installment_id: str, reason: str = "") -> bool:
        """
        Annule un versement
        """
        update_data = {
            "status": InstallmentStatus.CANCELLED,
            "notes": f"Annulé: {reason}",
            "updated_at": datetime.utcnow()
        }

        result = await self.collection.update_one(
            {"_id": ObjectId(installment_id)},
            {"$set": update_data}
        )

        return result.modified_count > 0

    async def get_installment_stats(self) -> dict:
        """
        Statistiques des versements
        """
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_amount": {"$sum": "$amount"},
                    "total_paid": {"$sum": "$paid_amount"}
                }
            }
        ]

        stats = {}
        total_installments = 0
        paid_installments = 0
        pending_installments = 0
        overdue_installments = 0
        total_amount = 0
        paid_amount = 0

        async for doc in self.collection.aggregate(pipeline):
            status = doc["_id"]
            count = doc["count"]
            amount = doc["total_amount"]
            paid = doc["total_paid"]

            stats[status] = {
                "count": count,
                "total_amount": amount,
                "total_paid": paid
            }

            total_installments += count
            total_amount += amount
            paid_amount += paid

            if status == InstallmentStatus.PAID:
                paid_installments = count
            elif status == InstallmentStatus.PENDING:
                pending_installments = count
            elif status == InstallmentStatus.OVERDUE:
                overdue_installments = count

        # Add summary stats
        stats["total_installments"] = total_installments
        stats["paid_installments"] = paid_installments
        stats["pending_installments"] = pending_installments
        stats["overdue_installments"] = overdue_installments
        stats["total_amount"] = total_amount
        stats["paid_amount"] = paid_amount

        return stats

    async def get_installments_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        status: Optional[InstallmentStatus] = None
    ) -> List[PaymentInstallmentPublic]:
        """
        Récupère les versements dans une plage de dates
        """
        query = {
            "created_at": {
                "$gte": start_date,
                "$lte": end_date
            }
        }

        if status:
            query["status"] = status

        cursor = self.collection.find(query).sort("created_at", -1)
        installments = []

        async for doc in cursor:
            # Convertir ObjectId en string
            doc["_id"] = str(doc["_id"])
            installments.append(PaymentInstallmentPublic(**doc))

        return installments

    async def search_installments_by_phone(
        self,
        phone: str,
        status: Optional[InstallmentStatus] = None
    ) -> List[dict]:
        """Recherche les versements via le téléphone stocké sur la commande."""
        phone = phone.strip()
        if not phone:
            return []

        orders = await db.orders.find(
            {"customer_phone": {"$regex": re.escape(phone), "$options": "i"}},
            {"_id": 1, "customer_name": 1, "customer_phone": 1}
        ).to_list(None)

        if not orders:
            return []

        orders_by_id = {str(order["_id"]): order for order in orders}
        query = {"order_id": {"$in": list(orders_by_id)}}
        if status:
            query["status"] = status.value

        cursor = self.collection.find(query).sort("due_date", 1)
        results = []
        async for doc in cursor:
            order = orders_by_id.get(doc.get("order_id"))
            if not order:
                continue

            doc["_id"] = str(doc["_id"])
            installment = PaymentInstallmentPublic(**doc).model_dump()
            installment["customer_name"] = order.get("customer_name")
            installment["customer_phone"] = order.get("customer_phone")
            results.append(installment)

        return results

# Instance globale du service
payment_installment_service = PaymentInstallmentService()
