from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from app.db.mongo import db
from app.models.promotion import (
    PromotionCreate, PromotionInDB, PromotionPublic, PromotionUpdate, PromotionStatus
)

class PromotionService:
    def __init__(self):
        self.promotions_collection = db.promotions

    async def create_promotion(self, promotion: PromotionCreate, created_by: str) -> PromotionPublic:
        """Crée une nouvelle promotion."""
        now = datetime.utcnow()

        # Vérifier s'il y a déjà une promotion active
        existing_active = await self.get_active_promotion()
        if existing_active:
            raise ValueError("Une promotion est déjà active. Désactivez-la d'abord.")

        promotion_data = {
            **promotion.dict(),
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
            "is_active": True
        }

        try:
            result = await self.promotions_collection.insert_one(promotion_data)
            promotion_data["id"] = str(result.inserted_id)

            return PromotionPublic(**promotion_data, status=PromotionStatus.ACTIVE)
        except Exception as e:
            print(f"Erreur création promotion : {e}")
            raise

    async def get_promotion(self, promotion_id: str) -> Optional[PromotionPublic]:
        """Récupère une promotion par son ID."""
        try:
            if not ObjectId.is_valid(promotion_id):
                return None

            promotion = await self.promotions_collection.find_one({
                "_id": ObjectId(promotion_id)
            })

            if not promotion:
                return None

            promotion["id"] = str(promotion["_id"])
            del promotion["_id"]

            # Déterminer le statut
            status = self._get_promotion_status(promotion)
            promotion["status"] = status

            return PromotionPublic(**promotion)
        except Exception as e:
            print(f"Erreur récupération promotion {promotion_id} : {e}")
            return None

    async def get_active_promotion(self) -> Optional[PromotionPublic]:
        """Récupère la promotion active en cours."""
        try:
            now = datetime.utcnow()
            print(f"DEBUG SERVICE: Now = {now}")

            query = {
                "is_active": True,
                "start_date": {"$lte": now},
                "end_date": {"$gte": now}
            }
            print(f"DEBUG SERVICE: Query = {query}")

            promotion = await self.promotions_collection.find_one(query)
            print(f"DEBUG SERVICE: Found promotion = {promotion}")

            if not promotion:
                print("DEBUG SERVICE: No promotion found matching criteria")
                return None

            promotion["id"] = str(promotion["_id"])
            del promotion["_id"]
            promotion["status"] = PromotionStatus.ACTIVE

            print(f"DEBUG SERVICE: Returning promotion: {promotion.get('name')}")
            return PromotionPublic(**promotion)
        except Exception as e:
            print(f"Erreur récupération promotion active : {e}")
            import traceback
            traceback.print_exc()
            return None

    async def get_all_promotions(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[PromotionPublic]:
        """Récupère toutes les promotions."""
        try:
            cursor = self.promotions_collection.find({}).skip(skip).limit(limit)
            promotions = []

            async for promotion in cursor:
                try:
                    promotion["id"] = str(promotion["_id"])
                    del promotion["_id"]

                    # Déterminer le statut
                    status = self._get_promotion_status(promotion)
                    promotion["status"] = status

                    promotions.append(PromotionPublic(**promotion))
                except Exception as e:
                    print(f"Erreur traitement promotion : {e}")
                    continue

            return promotions
        except Exception as e:
            print(f"Erreur récupération promotions : {e}")
            return []

    async def update_promotion(
        self,
        promotion_id: str,
        promotion_update: PromotionUpdate,
        updated_by: str
    ) -> Optional[PromotionPublic]:
        """Met à jour une promotion."""
        try:
            if not ObjectId.is_valid(promotion_id):
                return None

            update_data = promotion_update.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()

            # Vérifier les conflits si on active une promotion
            if update_data.get("is_active") == True:
                existing_active = await self.get_active_promotion()
                if existing_active and existing_active.id != promotion_id:
                    raise ValueError("Une autre promotion est déjà active")

            result = await self.promotions_collection.update_one(
                {"_id": ObjectId(promotion_id)},
                {"$set": update_data}
            )

            if result.modified_count:
                return await self.get_promotion(promotion_id)
            return None
        except Exception as e:
            print(f"Erreur mise à jour promotion : {e}")
            return None

    async def delete_promotion(self, promotion_id: str) -> bool:
        """Supprime une promotion."""
        try:
            if not ObjectId.is_valid(promotion_id):
                return False

            result = await self.promotions_collection.delete_one({
                "_id": ObjectId(promotion_id)
            })
            return result.deleted_count > 0
        except Exception as e:
            print(f"Erreur suppression promotion : {e}")
            return False

    async def deactivate_promotion(self, promotion_id: str) -> bool:
        """Désactive une promotion."""
        try:
            if not ObjectId.is_valid(promotion_id):
                return False

            result = await self.promotions_collection.update_one(
                {"_id": ObjectId(promotion_id)},
                {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Erreur désactivation promotion : {e}")
            return False

    def _get_promotion_status(self, promotion: dict) -> PromotionStatus:
        """Détermine le statut d'une promotion."""
        now = datetime.utcnow()

        if not promotion.get("is_active", False):
            return PromotionStatus.INACTIVE

        start_date = promotion.get("start_date")
        end_date = promotion.get("end_date")

        if start_date and end_date:
            if now < start_date:
                return PromotionStatus.INACTIVE
            elif now > end_date:
                return PromotionStatus.EXPIRED
            else:
                return PromotionStatus.ACTIVE

        return PromotionStatus.INACTIVE

    async def calculate_discounted_price(self, original_price: float) -> tuple[float, float]:
        """Calcule le prix réduit et le montant de la réduction."""
        try:
            promotion = await self.get_active_promotion()

            if not promotion or promotion.discount_percentage is None:
                return original_price, 0.0

            discount_percentage = float(promotion.discount_percentage)
            discount_amount = original_price * (discount_percentage / 100)
            discounted_price = original_price - discount_amount

            return round(discounted_price, 2), round(discount_amount, 2)
        except Exception as e:
            print(f"Erreur calcul prix réduit: {e}")
            return original_price, 0.0

promotion_service = PromotionService()
