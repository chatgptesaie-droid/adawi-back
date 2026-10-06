# === CORRECTIONS POUR PRODUCT_SERVICE.PY ===

from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.db.mongo import db
from app.models.product import (
    ProductCreate, ProductInDB, ProductPublic, ProductUpdate,
    CategoryCreate, CategoryInDB, CategoryPublic, CategoryUpdate
)
from app.services.newsletter_service import newsletter_service
from app.services.promotion_service import promotion_service

class ProductService:
    def __init__(self):
        self.products_collection = db.products
        self.categories_collection = db.categories

    # === PRODUITS ===
    async def create_product(self, product: ProductCreate, seller_id: str) -> ProductPublic:
        """Crée un nouveau produit."""
        now = datetime.utcnow()
        product_data = {
            **product.dict(),
            "seller_id": seller_id,
            "created_at": now,
            "updated_at": now,
            "is_active": True
        }

        try:
            result = await self.products_collection.insert_one(product_data)
            product_data["id"] = str(result.inserted_id)

            # Envoi email à tous les abonnés newsletter
            try:
                subject = f"Nouveau produit sur Showroom : {product_data['name']}"
                body = f"Bonjour,\n\nDécouvrez notre nouveau produit : {product_data['name']} !\n\nDescription : {product_data['description']}\nPrix : {product_data['price']} fcfa\n\nRendez-vous vite sur la boutique pour en profiter !"
                await newsletter_service.send_to_all(subject, body)
            except Exception as e:
                print(f"Erreur envoi newsletter : {e}")

            return ProductPublic(**product_data)
        except Exception as e:
            print(f"Erreur création produit : {e}")
            raise

    async def get_product(self, product_id: str) -> Optional[ProductPublic]:
        """Récupère un produit par son ID."""
        try:
            # Vérifier si product_id est un ObjectId valide
            if not ObjectId.is_valid(product_id):
                return None

            product = await self.products_collection.find_one({
                "_id": ObjectId(product_id),
                "is_active": True
            })

            if not product:
                return None

            product["id"] = str(product["_id"])
            del product["_id"]  # Supprimer _id pour éviter les conflits

            # Assurer que le prix est un float
            if "price" in product:
                try:
                    product["price"] = float(product["price"])
                except (ValueError, TypeError):
                    product["price"] = 0.0

            # Récupérer la catégorie si elle existe
            if product.get("category_id"):
                try:
                    category = await self.get_category(product["category_id"])
                    if category:
                        product["category"] = category.dict()
                except Exception as e:
                    print(f"Erreur récupération catégorie : {e}")
                    product["category"] = None

            # Calculer les prix réduits si promotion active
            await self._apply_promotion_to_product(product)

            return ProductPublic(**product)
        except Exception as e:
            print(f"Erreur récupération produit {product_id} : {e}")
            return None

    async def get_products(
        self,
        skip: int = 0,
        limit: int = 100000000,
        category_id: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        sizes: Optional[List[str]] = None,
        colors: Optional[List[str]] = None,
        search: Optional[str] = None,
        name: Optional[str] = None,
        seller_id: Optional[str] = None  # Ajout pour filtrer par vendeur
    ) -> List[ProductPublic]:
        """Récupère une liste de produits avec filtres."""
        try:
            filter_query = {"is_active": True}

            if category_id:
                if ObjectId.is_valid(category_id):
                    filter_query["category_id"] = category_id

            if seller_id:
                if ObjectId.is_valid(seller_id):
                    filter_query["seller_id"] = seller_id

            if min_price is not None or max_price is not None:
                price_filter = {}
                if min_price is not None:
                    price_filter["$gte"] = min_price
                if max_price is not None:
                    price_filter["$lte"] = max_price
                filter_query["price"] = price_filter

            if sizes:
                filter_query["sizes"] = {"$in": sizes}

            if colors:
                filter_query["colors"] = {"$in": colors}

            # Recherche textuelle - nécessite un index text
            if search:
                filter_query["$or"] = [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"description": {"$regex": search, "$options": "i"}},
                    {"tags": {"$in": [search]}}
                ]

            if name:
                filter_query["name"] = {"$regex": name, "$options": "i"}

            print(f"Requête MongoDB : {filter_query}")  # Debug

            cursor = self.products_collection.find(filter_query).skip(skip).limit(limit)
            products = []

            async for product in cursor:
                try:
                    product["id"] = str(product["_id"])
                    del product["_id"]

                    # Récupérer la catégorie si elle existe
                    if product.get("category_id"):
                        try:
                            category = await self.get_category(product["category_id"])
                            if category:
                                product["category"] = category.dict()
                        except Exception as e:
                            print(f"Erreur catégorie pour produit {product['id']} : {e}")
                            product["category"] = None

                    products.append(product)
                except Exception as e:
                    print(f"Erreur traitement produit : {e}")
                    continue

            # Appliquer les promotions à tous les produits récupérés
            await self._apply_promotion_to_products(products)

            # Convertir en ProductPublic après application des promotions
            result_products = []
            for product in products:
                try:
                    result_products.append(ProductPublic(**product))
                except Exception as e:
                    print(f"Erreur conversion ProductPublic : {e}")
                    continue

            print(f"Nombre de produits trouvés : {len(result_products)}")  # Debug
            return result_products

        except Exception as e:
            print(f"Erreur récupération produits : {e}")
            return []
        #-------------------------------------------------------------------------
    async def get_all_products_admin(
        self,
        skip: int = 0,
        limit: Optional[int] = None
        ) -> List[ProductPublic]:
        """Récupère tous les produits pour admin/vendeur (incluant inactifs)."""
        try:
            # Construction de la requête de base
            query = self.products_collection.find({}).skip(skip)

            # Application de la limite si spécifiée
            if limit is not None:
                query = query.limit(limit)

            products = []

            async for product in query:
                try:
                    # Conversion de l'ObjectId en string
                    product["id"] = str(product["_id"])
                    del product["_id"]

                    # Récupération de la catégorie associée
                    if product.get("category_id"):
                        try:
                            category = await self.get_category(product["category_id"])
                            product["category"] = category.dict() if category else None
                        except Exception as e:
                            print(f"Erreur récupération catégorie: {e}")
                            product["category"] = None

                    products.append(ProductPublic(**product))
                except Exception as e:
                    print(f"Erreur transformation produit: {e}")
                    continue

            return products
        except Exception as e:
            print(f"Erreur récupération produits admin: {e}")
            return []
        #----------------------------------------------------------------------
    async def update_product(self, product_id: str, product_update: ProductUpdate, seller_id: str) -> Optional[ProductPublic]:
        """Met à jour un produit. Tous les vendeurs et admins peuvent modifier tous les produits."""
        try:
            if not ObjectId.is_valid(product_id):
                return None

            update_data = product_update.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()

            # Tous les vendeurs et admins peuvent modifier tous les produits
            filter_query = {"_id": ObjectId(product_id)}

            # Vérifier si le produit existe
            existing_product = await self.products_collection.find_one(filter_query)
            if not existing_product:
                return None

            result = await self.products_collection.update_one(
                filter_query,
                {"$set": update_data}
            )

            if result.modified_count:
                # Récupérer le produit mis à jour sans filtrer par is_active
                updated_product = await self.products_collection.find_one({"_id": ObjectId(product_id)})
                if updated_product:
                    updated_product["id"] = str(updated_product["_id"])
                    del updated_product["_id"]

                    # Récupérer la catégorie si elle existe
                    if updated_product.get("category_id"):
                        try:
                            category = await self.get_category(updated_product["category_id"])
                            if category:
                                updated_product["category"] = category.dict()
                        except Exception as e:
                            print(f"Erreur récupération catégorie : {e}")
                            updated_product["category"] = None

                    return ProductPublic(**updated_product)
            return None
        except Exception as e:
            print(f"Erreur mise à jour produit : {e}")
            return None

    async def delete_product(self, product_id: str, seller_id: str, role: str) -> tuple[bool, str]:
        """Supprime un produit (soft delete pour vendeur, hard delete pour admin - incluant inactifs)."""
        try:
            if not ObjectId.is_valid(product_id):
                return False, "ID de produit invalide"

            # Vérifier d'abord si le produit existe
            existing_product = await self.products_collection.find_one({"_id": ObjectId(product_id)})
            if not existing_product:
                return False, "Produit non trouvé"

            is_active = existing_product.get("is_active", True)

            if role == "vendeur":
                # Vérifier si le produit est déjà inactif
                if not is_active:
                    return False, "Produit déjà supprimé"

                # Soft delete: désactiver le produit
                filter_query = {"_id": ObjectId(product_id)}

                result = await self.products_collection.update_one(
                    filter_query,
                    {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
                )

                if result.modified_count > 0:
                    return True, "Produit supprimé avec succès"
                else:
                    return False, "Échec de la suppression du produit"

            elif role == "admin":
                # Hard delete: suppression définitive (peut supprimer actifs et inactifs)
                result = await self.products_collection.delete_one({"_id": ObjectId(product_id)})

                if result.deleted_count > 0:
                    if is_active:
                        return True, "Produit supprimé définitivement"
                    else:
                        return True, "Produit inactif supprimé définitivement"
                else:
                    return False, "Échec de la suppression définitive du produit"

            else:
                return False, "Rôle non autorisé pour la suppression"

        except Exception as e:
            print(f"Erreur suppression produit : {e}")
            return False, f"Erreur serveur: {str(e)}"

    # === CATÉGORIES ===
    async def create_category(self, category: CategoryCreate) -> CategoryPublic:
        """Crée une nouvelle catégorie."""
        now = datetime.utcnow()
        category_data = {
            **category.dict(),
            "created_at": now,
            "updated_at": now
        }

        try:
            result = await self.categories_collection.insert_one(category_data)
            category_data["id"] = str(result.inserted_id)

            return CategoryPublic(**category_data)
        except Exception as e:
            print(f"Erreur création catégorie : {e}")
            raise

    async def get_category(self, category_id: str) -> Optional[CategoryPublic]:
        """Récupère une catégorie par son ID."""
        try:
            if not ObjectId.is_valid(category_id):
                return None

            category = await self.categories_collection.find_one({"_id": ObjectId(category_id)})
            if not category:
                return None

            category["id"] = str(category["_id"])
            del category["_id"]
            return CategoryPublic(**category)
        except Exception as e:
            print(f"Erreur récupération catégorie : {e}")
            return None

    async def get_categories(self, parent_id: Optional[str] = None) -> List[CategoryPublic]:
        """Récupère les catégories."""
        try:
            filter_query = {}
            if parent_id:
                if ObjectId.is_valid(parent_id):
                    filter_query["parent_id"] = parent_id
            else:
                # Catégories racines : parent_id est None, null, ou non défini
                filter_query["$or"] = [
                    {"parent_id": None},
                    {"parent_id": {"$exists": False}},  # parent_id non défini
                    {"parent_id": ""}  # parent_id vide
                ]

            cursor = self.categories_collection.find(filter_query)
            categories = []

            async for category in cursor:
                try:
                    category["id"] = str(category["_id"])
                    del category["_id"]
                    categories.append(CategoryPublic(**category))
                except Exception as e:
                    print(f"Erreur traitement catégorie : {e}")
                    continue

            return categories
        except Exception as e:
            print(f"Erreur récupération catégories : {e}")
            return []

    async def update_category(self, category_id: str, category_update: CategoryUpdate) -> Optional[CategoryPublic]:
        """Met à jour une catégorie."""
        try:
            if not ObjectId.is_valid(category_id):
                return None

            update_data = category_update.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow()

            result = await self.categories_collection.update_one(
                {"_id": ObjectId(category_id)},
                {"$set": update_data}
            )

            if result.modified_count:
                return await self.get_category(category_id)
            return None
        except Exception as e:
            print(f"Erreur mise à jour catégorie : {e}")
            return None

    async def delete_category(self, category_id: str) -> bool:
        """Supprime une catégorie."""
        try:
            if not ObjectId.is_valid(category_id):
                return False

            # Vérifier s'il y a des produits dans cette catégorie
            product_count = await self.products_collection.count_documents({
                "category_id": category_id,
                "is_active": True
            })

            if product_count > 0:
                return False  # Ne pas supprimer si des produits existent

            result = await self.categories_collection.delete_one({"_id": ObjectId(category_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Erreur suppression catégorie : {e}")
            return False

    # === MÉTHODES POUR LES PROMOTIONS ===
    async def _apply_promotion_to_product(self, product: dict) -> None:
        """Applique la promotion active à un produit."""
        try:
            price = product.get("price") or 0
            discounted_price, discount_amount = await promotion_service.calculate_discounted_price(price)

            if discounted_price < price:
                product["discounted_price"] = discounted_price
                product["discount_amount"] = discount_amount
            else:
                product["discounted_price"] = None
                product["discount_amount"] = None
        except Exception as e:
            print(f"Erreur application promotion au produit {product.get('id', 'unknown')}: {e}")
            product["discounted_price"] = None
            product["discount_amount"] = None

    async def _apply_promotion_to_products(self, products: List[dict]) -> None:
        """Applique la promotion active à une liste de produits."""
        try:
            # Récupérer la promotion active une seule fois
            promotion = await promotion_service.get_active_promotion()

            if not promotion:
                # Pas de promotion active, définir tous les prix réduits à None
                for product in products:
                    product["discounted_price"] = None
                    product["discount_amount"] = None
                return

            discount_percentage = promotion.discount_percentage

            # Appliquer la promotion à tous les produits
            for product in products:
                try:
                    original_price = product.get("price", 0)
                    discount_amount = original_price * (discount_percentage / 100)
                    discounted_price = original_price - discount_amount

                    product["discounted_price"] = round(discounted_price, 2)
                    product["discount_amount"] = round(discount_amount, 2)
                except Exception as e:
                    print(f"Erreur application promotion au produit {product.get('id', 'unknown')}: {e}")
                    product["discounted_price"] = None
                    product["discount_amount"] = None
        except Exception as e:
            print(f"Erreur application promotion aux produits: {e}")
            for product in products:
                product["discounted_price"] = None
                product["discount_amount"] = None

    async def get_product_with_discount(self, product_id: str) -> Optional[dict]:
        """Récupère un produit avec son prix réduit appliqué."""
        try:
            # Vérifier si product_id est un ObjectId valide
            if not ObjectId.is_valid(product_id):
                return None

            product = await self.products_collection.find_one({
                "_id": ObjectId(product_id),
                "is_active": True
            })

            if not product:
                return None

            product["id"] = str(product["_id"])
            del product["_id"]  # Supprimer _id pour éviter les conflits

            # Assurer que le prix est un float
            if "price" in product:
                try:
                    product["price"] = float(product["price"])
                except (ValueError, TypeError):
                    product["price"] = 0.0

            # Récupérer la catégorie si elle existe
            if product.get("category_id"):
                try:
                    category = await self.get_category(product["category_id"])
                    if category:
                        product["category"] = category.dict()
                except Exception as e:
                    print(f"Erreur récupération catégorie : {e}")
                    product["category"] = None

            # Calculer les prix réduits si promotion active
            await self._apply_promotion_to_product(product)

            return product
        except Exception as e:

            async def update_product_images(self, product_id: str, update_data: dict) -> bool:
                """Met à jour les images d'un produit (utilisé pour les uploads en background)."""
                try:
                    if not ObjectId.is_valid(product_id):
                        return False

                    update_data["updated_at"] = datetime.utcnow()

                    result = await self.products_collection.update_one(
                        {"_id": ObjectId(product_id)},
                        {"$set": update_data}
                    )

                    return result.modified_count > 0
                except Exception as e:
                    print(f"Erreur mise à jour images produit {product_id}: {e}")
                    return False

                    print(f"Erreur récupération produit avec discount {product_id} : {e}")
                    return None

product_service = ProductService()
