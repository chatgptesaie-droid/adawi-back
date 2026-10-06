import logging
from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from app.db.mongo import db
from app.models.cart import CartCreate, CartUpdate, CartInDB, CartPublic, CartItem
from app.services.product_service import product_service

logger = logging.getLogger(__name__)

class CartService:
    def __init__(self):
        self.collection = db.carts

    async def get_cart(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> Optional[CartPublic]:
        query = {}
        if user_id:
            query["user_id"] = user_id
        elif session_id:
            query["session_id"] = session_id
        else:
            return None
        cart = await self.collection.find_one(query)
        if not cart:
            return None
        cart["id"] = str(cart["_id"])
        # Enrichir chaque item avec le prix (réduit si promotion), le nom et les images du produit
        enriched_items = []
        for item in cart.get("items", []):
            try:
                # Utiliser le service produit pour obtenir les prix avec promotion
                product_with_discount = await product_service.get_product_with_discount(item["product_id"])
                if product_with_discount:
                    original_price = product_with_discount.get("price") or 0.0
                    discounted_price = product_with_discount.get("discounted_price") or original_price
                    name = product_with_discount.get("name", "")
                    images = product_with_discount.get("images", [])
                    discount_amount = product_with_discount.get("discount_amount", 0.0)
                    price = discounted_price  # price reste le prix réduit pour compatibilité
                else:
                    # Fallback si le produit n'est pas trouvé
                    try:
                        product = await db.products.find_one({"_id": ObjectId(item["product_id"])})
                    except:
                        product = None
                    original_price = (product.get("price") if product else None) or 0.0
                    discounted_price = original_price
                    name = product.get("name", "") if product else ""
                    images = product.get("images", []) if product else []
                    discount_amount = 0.0
                    price = original_price
            except Exception as e:
                logger.error(f"Erreur lors de l'enrichissement de l'item {item.get('product_id', 'unknown')}: {e}")
                # Valeurs par défaut en cas d'erreur - essayer de récupérer le prix depuis l'item si disponible
                original_price = item.get("original_price", 0.0) or 0.0
                discounted_price = item.get("discounted_price", original_price) or original_price
                name = item.get("name", "")
                images = item.get("images", [])
                discount_amount = item.get("discount_amount", 0.0) or 0.0
                price = item.get("price", discounted_price) or discounted_price

            enriched_item = {
                **item,
                "original_price": original_price,
                "price": price,
                "discounted_price": discounted_price,
                "name": name,
                "images": images,
                "discount_amount": discount_amount
            }
            enriched_items.append(enriched_item)
        cart["items"] = enriched_items
        return CartPublic(**cart)

    async def create_cart(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        now = datetime.utcnow()
        cart_data = {
            "user_id": user_id,
            "session_id": session_id,
            "items": [],
            "created_at": now,
            "updated_at": now
        }
        result = await self.collection.insert_one(cart_data)
        cart_data["id"] = str(result.inserted_id)
        return CartPublic(**cart_data)

    async def add_or_update_item(self, item: CartItem, user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        logger.info(f"Ajout/mise à jour item: {item.product_id}, qty: {item.quantity}, size: {item.size}, color: {item.color}, user_id: {user_id}, session_id: {session_id}")
        cart = await self.get_cart(user_id, session_id)
        if not cart:
            cart = await self.create_cart(user_id, session_id)
        # Construire la liste des items en plain (seulement les champs de base)
        plain_items = []
        item_dict = item.dict()
        found = False
        for cart_item in cart.items:
            plain_item = {
                "product_id": cart_item.product_id,
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "color": cart_item.color
            }
            if cart_item.product_id == item_dict["product_id"] and cart_item.size == item_dict.get("size") and cart_item.color == item_dict.get("color"):
                plain_item["quantity"] = item_dict["quantity"]
                found = True
            plain_items.append(plain_item)
        if not found:
            plain_items.append({
                "product_id": item.product_id,
                "quantity": item.quantity,
                "size": item.size,
                "color": item.color
            })
        # Mettre à jour en base avec les items plain
        await self.collection.update_one(
            {"_id": ObjectId(cart.id)},
            {"$set": {"items": plain_items, "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Item ajouté/mis à jour avec succès pour cart {cart.id}")
        return await self.get_cart(user_id, session_id)

    async def remove_item(self, product_id: str, size: Optional[str] = None, color: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        logger.info(f"Suppression item: {product_id}, size: {size}, color: {color}, user_id: {user_id}, session_id: {session_id}")
        cart = await self.get_cart(user_id, session_id)
        if not cart:
            return None
        # Reconstruire les items plain en filtrant
        plain_items = []
        for cart_item in cart.items:
            if not (cart_item.product_id == product_id and (size is None or cart_item.size == size) and (color is None or cart_item.color == color)):
                plain_item = {
                    "product_id": cart_item.product_id,
                    "quantity": cart_item.quantity,
                    "size": cart_item.size,
                    "color": cart_item.color
                }
                plain_items.append(plain_item)
        await self.collection.update_one(
            {"_id": ObjectId(cart.id)},
            {"$set": {"items": plain_items, "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Item supprimé avec succès pour cart {cart.id}")
        return await self.get_cart(user_id, session_id)

    async def clear_cart(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        logger.info(f"Vider panier: user_id: {user_id}, session_id: {session_id}")
        cart = await self.get_cart(user_id=user_id, session_id=session_id)
        if not cart:
            cart = await self.create_cart(user_id=user_id, session_id=session_id)
        await self.collection.update_one(
            {"_id": ObjectId(cart.id)},
            {"$set": {"items": [], "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Panier vidé avec succès pour cart {cart.id}")
        return await self.get_cart(user_id=user_id, session_id=session_id)

    async def update_item_quantity(self, product_id: str, quantity: int, size: Optional[str] = None, color: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        if quantity <= 0:
            raise ValueError("La quantité doit être supérieure à 0")
        logger.info(f"Mise à jour quantité: {product_id}, qty: {quantity}, size: {size}, color: {color}, user_id: {user_id}, session_id: {session_id}")
        cart = await self.get_cart(user_id, session_id)
        if not cart:
            raise ValueError("Panier non trouvé")
        # Reconstruire les items plain
        plain_items = []
        found = False
        for cart_item in cart.items:
            plain_item = {
                "product_id": cart_item.product_id,
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "color": cart_item.color
            }
            if cart_item.product_id == product_id and (size is None or cart_item.size == size) and (color is None or cart_item.color == color):
                plain_item["quantity"] = quantity
                found = True
            plain_items.append(plain_item)
        if not found:
            raise ValueError("Produit non trouvé dans le panier")
        # Mettre à jour en base avec les items plain
        await self.collection.update_one(
            {"_id": ObjectId(cart.id)},
            {"$set": {"items": plain_items, "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Quantité mise à jour avec succès pour cart {cart.id}")
        return await self.get_cart(user_id, session_id)

    async def increase_item(self, product_id: str, size: Optional[str] = None, color: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        logger.info(f"Incrémenter item: {product_id}, size: {size}, color: {color}, user_id: {user_id}, session_id: {session_id}")
        cart = await self.get_cart(user_id, session_id)
        if not cart:
            raise ValueError("Panier non trouvé")
        # Reconstruire les items plain
        plain_items = []
        found = False
        for cart_item in cart.items:
            plain_item = {
                "product_id": cart_item.product_id,
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "color": cart_item.color
            }
            if cart_item.product_id == product_id and (size is None or cart_item.size == size) and (color is None or cart_item.color == color):
                plain_item["quantity"] += 1
                found = True
            plain_items.append(plain_item)
        if not found:
            raise ValueError("Produit non trouvé dans le panier")
        # Mettre à jour en base avec les items plain
        await self.collection.update_one(
            {"_id": ObjectId(cart.id)},
            {"$set": {"items": plain_items, "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Item incrémenté avec succès pour cart {cart.id}")
        return await self.get_cart(user_id, session_id)

    async def decrease_item(self, product_id: str, size: Optional[str] = None, color: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        logger.info(f"Décrémenter item: {product_id}, size: {size}, color: {color}, user_id: {user_id}, session_id: {session_id}")
        cart = await self.get_cart(user_id, session_id)
        if not cart:
            raise ValueError("Panier non trouvé")
        # Reconstruire les items plain
        plain_items = []
        found = False
        for cart_item in cart.items:
            plain_item = {
                "product_id": cart_item.product_id,
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "color": cart_item.color
            }
            if cart_item.product_id == product_id and (size is None or cart_item.size == size) and (color is None or cart_item.color == color):
                if cart_item.quantity > 1:
                    plain_item["quantity"] -= 1
                else:
                    raise ValueError("La quantité ne peut pas être inférieure à 1. Utilisez la suppression pour retirer le produit.")
                found = True
            plain_items.append(plain_item)
        if not found:
            raise ValueError("Produit non trouvé dans le panier")
        # Mettre à jour en base avec les items plain
        await self.collection.update_one(
            {"_id": ObjectId(cart.id)},
            {"$set": {"items": plain_items, "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Item décrémenté avec succès pour cart {cart.id}")
        return await self.get_cart(user_id, session_id)

    async def batch_update(self, updates: List[dict], user_id: Optional[str] = None, session_id: Optional[str] = None) -> CartPublic:
        logger.info(f"Batch update: {len(updates)} updates, user_id: {user_id}, session_id: {session_id}")
        cart = await self.get_cart(user_id, session_id)
        if not cart:
            raise ValueError("Panier non trouvé")
        # Reconstruire les items plain avec les mises à jour
        plain_items = []
        for cart_item in cart.items:
            plain_item = {
                "product_id": cart_item.product_id,
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "color": cart_item.color
            }
            # Vérifier si cet item doit être mis à jour
            for update in updates:
                product_id = update["product_id"]
                quantity = update["quantity"]
                size = update.get("size")
                color = update.get("color")
                if quantity <= 0:
                    raise ValueError(f"La quantité doit être supérieure à 0 pour {product_id}")
                if cart_item.product_id == product_id and (size is None or cart_item.size == size) and (color is None or cart_item.color == color):
                    plain_item["quantity"] = quantity
                    break
            plain_items.append(plain_item)
        # Vérifier que tous les updates ont été appliqués
        for update in updates:
            product_id = update["product_id"]
            size = update.get("size")
            color = update.get("color")
            found = any(item["product_id"] == product_id and (size is None or item.get("size") == size) and (color is None or item.get("color") == color) for item in plain_items)
            if not found:
                raise ValueError(f"Produit non trouvé dans le panier: {product_id} (size={size}, color={color})")
        # Mettre à jour en base avec les items plain
        await self.collection.update_one(
            {"_id": ObjectId(cart.id)},
            {"$set": {"items": plain_items, "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Batch update réussi pour cart {cart.id}")
        return await self.get_cart(user_id, session_id)

cart_service = CartService()
