from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from app.db.mongo import db
from app.models.refund import (
    RefundCreate, RefundInDB, RefundPublic, RefundUpdate,
    RefundStatus, RefundItem
)
from app.models.order import OrderPublic, PaymentStatus
from app.services.notification_service import notification_service
from app.core.emails_utils import notify_admin_of_refund_request
from app.services.sms_service import customer_name as sms_customer_name
from app.services.sms_service import customer_phone, send_customer_sms, short_reference, status_label

class RefundService:
    def __init__(self):
        self.refunds = db.refunds
        self.orders = db.orders

    async def create_refund(self, user_id: str, data: RefundCreate) -> RefundPublic:
        # Vérifier commande
        order = await self.orders.find_one({"_id": ObjectId(data.order_id)})
        if not order:
            raise ValueError("Order not found")
        if order.get("payment_status") != PaymentStatus.effectue.value:
            raise ValueError("Order not paid")
        # Calcul montant
        if not data.items:
            amount = order.get("total", 0.0)  # remboursement total
            items_payload = []
        else:
            order_items_index = {it["product_id"]: it for it in order.get("items", [])}
            amount = 0.0
            items_payload = []
            for it in data.items:
                oi = order_items_index.get(it.product_id)
                if not oi:
                    raise ValueError("Invalid product in refund")
                if it.quantity > oi.get("quantity", 0):
                    raise ValueError("Quantity exceeds order item")
                line_total = it.unit_price * it.quantity
                amount += line_total
                items_payload.append(it.dict())
        now = datetime.utcnow()
        payload = {
            "order_id": data.order_id,
            "user_id": user_id,
            "reason": data.reason.value,
            "comment": data.comment,
            "items": items_payload,
            "amount": amount,
            "status": RefundStatus.pending.value,
            "created_at": now,
            "updated_at": now,
            "admin_comment": None
        }
        res = await self.refunds.insert_one(payload)
        payload["id"] = str(res.inserted_id)

        # Get user info for notifications and email
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        customer_name = user.get("full_name", "Client") if user else "Client"
        customer_email = user.get("email", "") if user else ""

        # Create notifications for staff and client
        await notification_service.notify_refund_requested(
            user_id=user_id,
            refund_id=payload["id"],
            reason=data.reason.value,
            amount=amount
        )

        # Send email to admin
        await notify_admin_of_refund_request(
            customer_name, customer_email, amount, payload["id"], data.reason.value
        )
        await send_customer_sms(
            customer_phone(user),
            sms_customer_name(user),
            f"Votre demande de remboursement de {amount:.0f} FCFA a été reçue (réf. {short_reference(payload['id'])}).",
            occurred_at=now,
            event="refund.created",
        )
        
        return RefundPublic(**payload)

    async def list_refunds(self, status: Optional[str] = None, user_id: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[RefundPublic]:
        q = {}
        if status:
            q["status"] = status
        if user_id:
            q["user_id"] = user_id
        cursor = self.refunds.find(q).sort("created_at", -1).skip(skip).limit(limit)
        results: List[RefundPublic] = []
        async for doc in cursor:
            doc["id"] = str(doc["_id"])
            results.append(RefundPublic(**doc))
        return results

    async def get_refund(self, refund_id: str) -> Optional[RefundPublic]:
        doc = await self.refunds.find_one({"_id": ObjectId(refund_id)})
        if not doc:
            return None
        doc["id"] = str(doc["_id"])
        return RefundPublic(**doc)

    async def update_refund(self, refund_id: str, data: RefundUpdate, admin_id: str) -> Optional[RefundPublic]:
        # Get current refund to track status changes
        current_refund = await self.refunds.find_one({"_id": ObjectId(refund_id)})
        if not current_refund:
            return None

        old_status = current_refund.get("status")
        new_status = data.status.value
        refund_amount = current_refund.get("amount", 0.0)

        now = datetime.utcnow()
        update = {"status": new_status, "updated_at": now}
        if data.admin_comment is not None:
            update["admin_comment"] = data.admin_comment

        # Handle revenue impact for status changes
        if old_status != new_status:
            await self._handle_revenue_impact(old_status, new_status, refund_amount, refund_id, admin_id)

        res = await self.refunds.update_one({"_id": ObjectId(refund_id)}, {"$set": update})
        if not res.modified_count:
            return None
        if old_status != new_status:
            refund = await self.refunds.find_one({"_id": ObjectId(refund_id)})
            user = await db.users.find_one({"_id": ObjectId(refund["user_id"])}) if refund else None
            await send_customer_sms(
                customer_phone(user),
                sms_customer_name(user),
                f"Le statut de votre remboursement {short_reference(refund_id)} est maintenant {status_label(new_status)}.",
                occurred_at=now,
                event="refund.status_changed",
            )
        return await self.get_refund(refund_id)

    async def _handle_revenue_impact(self, old_status: str, new_status: str, amount: float, refund_id: str, admin_id: str):
        """Handle revenue impact when refund status changes to/from processed"""
        from app.models.refund import RefundStatus

        # Revenue impact logic:
        # - When status changes TO "processed": deduct amount from revenue
        # - When status changes FROM "processed" TO other: add amount back to revenue

        revenue_adjustment = 0.0
        adjustment_reason = ""

        if new_status == RefundStatus.processed.value and old_status != RefundStatus.processed.value:
            # Status changed to "processed" - deduct from revenue
            revenue_adjustment = -amount
            adjustment_reason = f"Refund {refund_id} marked as processed"
        elif old_status == RefundStatus.processed.value and new_status != RefundStatus.processed.value:
            # Status changed from "processed" to other - add back to revenue
            revenue_adjustment = amount
            adjustment_reason = f"Refund {refund_id} status changed from processed to {new_status}"

        if revenue_adjustment != 0.0:
            # Log the revenue adjustment for audit purposes
            adjustment_doc = {
                "refund_id": refund_id,
                "old_status": old_status,
                "new_status": new_status,
                "amount": amount,
                "revenue_adjustment": revenue_adjustment,
                "reason": adjustment_reason,
                "admin_id": admin_id,
                "timestamp": datetime.utcnow()
            }

            # Store adjustment in a revenue_adjustments collection for audit
            revenue_adjustments = db.revenue_adjustments
            await revenue_adjustments.insert_one(adjustment_doc)

            # Note: The actual revenue calculation will be handled in dashboard_service.py
            # This method just tracks the adjustments for audit purposes

    async def aggregate_stats(self):
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}, "amount": {"$sum": "$amount"}}}
        ]
        stats = {"counts": {}, "amounts": {}, "total_amount": 0.0}
        async for row in self.refunds.aggregate(pipeline):
            st = row["_id"]
            stats["counts"][st] = row["count"]
            stats["amounts"][st] = row["amount"]
            # total_amount = somme des montants des remboursements "processed" uniquement
            if st == "processed":
                stats["total_amount"] += row["amount"]
        return stats

refund_service = RefundService()
