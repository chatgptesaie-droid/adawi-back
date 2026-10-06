from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form, BackgroundTasks
from typing import Optional, List
import json
import asyncio
import uuid
from app.models.product import (
    ProductCreate, ProductPublic, ProductUpdate,
    CategoryCreate, CategoryPublic, CategoryUpdate
)
from app.services.product_service import product_service
from app.api.auth import get_current_user
from app.models.user import UserPublic
import logging
import cloudinary
import cloudinary.uploader
from app.core.config import settings

# Configuration du logging pour debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration Cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

router = APIRouter(prefix="/products", tags=["products"])

# === ROUTES PRODUITS ===

@router.get("/", response_model=List[ProductPublic])
async def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(None, ge=1, le=100000000),
    category_id: Optional[str] = None,
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    sizes: Optional[List[str]] = Query(None),
    colors: Optional[List[str]] = Query(None),
    search: Optional[str] = None,
    name: Optional[str] = None
):
    """Récupère une liste de produits avec filtres (publique)."""
    try:
        logger.info(f"Récupération produits - skip: {skip}, limit: {limit}")
        products = await product_service.get_products(
            skip=skip,
            limit=limit,
            category_id=category_id,
            min_price=min_price,
            max_price=max_price,
            sizes=sizes,
            colors=colors,
            search=search,
            name=name
        )
        logger.info(f"Nombre de produits trouvés: {len(products)}")
        return products
    except Exception as e:
        logger.error(f"Erreur récupération produits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/admin/all", response_model=List[ProductPublic])
async def get_all_products_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(None, ge=1, le=100000000),
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupère tous les produits pour admin/vendeur (incluant inactifs)."""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Admin/vendeur requis")

    try:
        logger.info(f"Admin {current_user.email} récupère tous les produits")
        products = await product_service.get_all_products_admin(skip=skip, limit=limit)
        logger.info(f"Produits admin trouvés: {len(products)}")
        return products
    except Exception as e:
        logger.error(f"Erreur récupération produits admin: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/vendor/my-products", response_model=List[ProductPublic])
async def get_my_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(None, ge=1, le=100000000),  # Limite augmentée
    current_user: UserPublic = Depends(get_current_user)
):
    """Récupère tous les produits pour le vendeur/admin (incluant inactifs)."""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur requis")

    try:
        logger.info(f"Vendeur {current_user.email} récupère tous les produits")
        # Le vendeur voit maintenant tous les produits comme l'admin
        products = await product_service.get_all_products_admin(skip=skip, limit=limit)
        logger.info(f"Tous les produits trouvés pour vendeur: {len(products)}")
        return products
    except Exception as e:
        logger.error(f"Erreur récupération tous les produits pour vendeur: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/{product_id}", response_model=ProductPublic)
async def get_product(product_id: str):
    """Récupère un produit par son ID."""
    try:
        logger.info(f"Récupération produit ID: {product_id}")
        product = await product_service.get_product(product_id)
        if not product:
            logger.warning(f"Produit non trouvé: {product_id}")
            raise HTTPException(status_code=404, detail="Produit non trouvé")
        return product
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération produit {product_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

# Fonctions utilitaires pour parser les listes
def parse_list_field(field):
    """Parse les tailles avec validation."""
    if field is None or field == '[""]' or field == '[]':
        return []
    try:
        if isinstance(field, str):
            values = json.loads(field)
        else:
            values = field
    except json.JSONDecodeError:
        values = [item.strip() for item in str(field).split(",") if item.strip()]

    # Normaliser en majuscules pour les tailles
    allowed = {"XS", "S", "M", "L", "XL", "XXL"}
    result = [v.upper() for v in values if v.upper() in allowed]
    return result

def parse_list_any(field):
    """Parse n'importe quelle liste de chaînes."""
    if field is None or field == '[""]' or field == '[]':
        return []
    try:
        if isinstance(field, str):
            values = json.loads(field)
        else:
            values = field
        if isinstance(values, list):
            return [str(v).strip() for v in values if str(v).strip()]
        return []
    except json.JSONDecodeError:
        return [item.strip() for item in str(field).split(",") if item.strip()]

async def upload_product_images_background(product_id: str, images: List[UploadFile], hover_images: List[UploadFile]):
    """Background task pour uploader les images du produit et mettre à jour le produit"""
    try:
        # Traiter les images principales
        image_urls = []
        if images:
            for image in images:
                if image.filename and image.content_type and image.content_type.startswith('image/'):
                    try:
                        # Lire le contenu du fichier
                        contents = await image.read()

                        # Upload vers Cloudinary
                        upload_result = await asyncio.wait_for(
                            asyncio.to_thread(
                                cloudinary.uploader.upload,
                                contents,
                                folder="products",
                                public_id=f"{product_id}_{uuid.uuid4().hex}",
                                resource_type="image",
                                quality="auto"
                            ),
                            timeout=300.0  # 5 minutes timeout pour Render
                        )

                        image_urls.append(upload_result['secure_url'])
                        logger.info(f"Image uploadée vers Cloudinary: {upload_result['secure_url']}")

                    except asyncio.TimeoutError:
                        logger.error(f"Timeout upload Cloudinary pour {image.filename}")
                    except Exception as e:
                        logger.error(f"Erreur upload Cloudinary pour {image.filename}: {str(e)}")

        # Traiter les images de survol
        hover_image_urls = []
        if hover_images:
            for image in hover_images:
                if image.filename and image.content_type and image.content_type.startswith('image/'):
                    try:
                        # Lire le contenu du fichier
                        contents = await image.read()

                        # Upload vers Cloudinary
                        upload_result = await asyncio.wait_for(
                            asyncio.to_thread(
                                cloudinary.uploader.upload,
                                contents,
                                folder="products/hover",
                                public_id=f"{product_id}_{uuid.uuid4().hex}",
                                resource_type="image",
                                quality="auto"
                            ),
                            timeout=300.0  # 5 minutes timeout pour Render
                        )

                        hover_image_urls.append(upload_result['secure_url'])
                        logger.info(f"Image de survol uploadée vers Cloudinary: {upload_result['secure_url']}")

                    except asyncio.TimeoutError:
                        logger.error(f"Timeout upload Cloudinary pour {image.filename}")
                    except Exception as e:
                        logger.error(f"Erreur upload Cloudinary pour {image.filename}: {str(e)}")

        # Update the product with the image URLs
        update_data = {}
        if image_urls:
            update_data["images"] = image_urls
        if hover_image_urls:
            update_data["hover_images"] = hover_image_urls

        if update_data:
            await product_service.update_product_images(product_id, update_data)
            logger.info(f"Background upload completed for product {product_id}")

    except Exception as e:
        logger.error(f"Background upload error for product {product_id}: {str(e)}")

@router.post("/", response_model=ProductPublic)
async def create_product(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(..., gt=0),
    cost_price: float = Form(0, ge=0, description="Prix de revient unitaire"),
    category_id: str = Form(...),
    stock: int = Form(..., ge=0),
    low_stock_threshold: int = Form(0, ge=0, description="Seuil d'alerte stock"),
    sizes: str = Form('[]', description='Liste des tailles, ex: ["S","M","L"]'),
    colors: str = Form('[]', description='Liste des couleurs, ex: ["Blanc","Noir"]'),
    tags: str = Form('[]', description='Liste des tags, ex: ["bio","premium"]'),
    images: List[UploadFile] = File([]),
    hover_images: List[UploadFile] = File([], description="Images affichées au survol"),
    current_user: UserPublic = Depends(get_current_user)
):
    """Crée un nouveau produit avec images uploadées (vendeur/admin uniquement)."""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur/Admin requis")

    try:
        logger.info(f"Création produit par {current_user.email}: {name}")

        # Parser les listes
        sizes_list = parse_list_field(sizes)
        colors_list = parse_list_any(colors)
        tags_list = parse_list_any(tags)

        logger.info(f"Sizes parsed: {sizes_list}, Colors: {colors_list}, Tags: {tags_list}")

        # Créer l'objet produit sans images
        product_data = {
            "name": name,
            "description": description,
            "price": price,
            "cost_price": cost_price,
            "currency": "XOF",  # Ajout du champ manquant
            "category_id": category_id,
            "stock": stock,
            "low_stock_threshold": low_stock_threshold,  # Ajout du champ manquant
            "sizes": sizes_list,
            "colors": colors_list,
            "tags": tags_list,
            "images": [],  # Images seront ajoutées en background
            "hover_images": []  # Images de survol seront ajoutées en background
        }

        logger.info(f"Données produit: {product_data}")

        product = ProductCreate(**product_data)
        new_product = await product_service.create_product(product, current_user.id)

        # Si des images sont fournies, ajouter task background pour upload
        if images or hover_images:
            background_tasks.add_task(upload_product_images_background, new_product.id, images, hover_images)

        logger.info(f"Produit créé avec succès: {new_product.id}")
        return new_product

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur création produit: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création: {str(e)}")

@router.put("/{product_id}", response_model=ProductPublic)
async def update_product(
    product_id: str,
    background_tasks: BackgroundTasks,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    price: Optional[float] = Form(None, gt=0),
    cost_price: Optional[float] = Form(None, ge=0),
    category_id: Optional[str] = Form(None),
    stock: Optional[int] = Form(None, ge=0),
    low_stock_threshold: Optional[int] = Form(None, ge=0),
    is_active: Optional[bool] = Form(None, description="Activer ou désactiver le produit"),
    sizes: Optional[str] = Form(None, description='Liste des tailles, ex: ["S","M","L"]'),
    colors: Optional[str] = Form(None, description='Liste des couleurs, ex: ["Blanc","Noir"]'),
    tags: Optional[str] = Form(None, description='Liste des tags, ex: ["bio","premium"]'),
    images: List[UploadFile] = File([]),
    hover_images: List[UploadFile] = File([], description="Nouvelles images de survol"),
    current_user: UserPublic = Depends(get_current_user)
):
    """Met à jour un produit (remplace toutes les images si fournies)."""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur/Admin requis")

    try:
        logger.info(f"Mise à jour produit {product_id} par {current_user.email}")

        update_data = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if price is not None:
            update_data["price"] = price
        if cost_price is not None:
            update_data["cost_price"] = cost_price
        if category_id is not None:
            update_data["category_id"] = category_id
        if stock is not None:
            update_data["stock"] = stock
        if low_stock_threshold is not None:
            update_data["low_stock_threshold"] = low_stock_threshold
        if is_active is not None:
            update_data["is_active"] = is_active
        if sizes is not None:
            update_data["sizes"] = parse_list_field(sizes)
        if colors is not None:
            update_data["colors"] = parse_list_any(colors)
        if tags is not None:
            update_data["tags"] = parse_list_any(tags)

        # Gérer les images principales - seulement si des images sont fournies
        if images and any(img.filename for img in images):
            # Utiliser la tâche en arrière-plan pour éviter les timeouts
            background_tasks.add_task(upload_product_images_background, product_id, images, [])

        # Gérer les images de survol - seulement si des images sont fournies
        if hover_images and any(img.filename for img in hover_images):
            # Utiliser la tâche en arrière-plan pour éviter les timeouts
            background_tasks.add_task(upload_product_images_background, product_id, [], hover_images)

        logger.info(f"Données de mise à jour: {update_data}")

        # Déterminer seller_id pour la mise à jour
        seller_id = current_user.id
        if current_user.role in ["admin", "vendeur"]:
            seller_id = "admin"  # Admin et vendeur peuvent modifier tous les produits

        product_update = ProductUpdate(**update_data)
        updated_product = await product_service.update_product(product_id, product_update, seller_id)

        if not updated_product:
            logger.warning(f"Produit non trouvé ou accès refusé: {product_id}")
            raise HTTPException(status_code=404, detail="Produit non trouvé ou accès refusé")

        logger.info(f"Produit mis à jour avec succès: {product_id}")
        return updated_product

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur mise à jour produit {product_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour: {str(e)}")

@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: UserPublic = Depends(get_current_user)
):
    """Supprime un produit (vendeur: soft delete, admin: hard delete)."""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur/Admin requis")

    try:
        logger.info(f"Suppression produit {product_id} par {current_user.email} ({current_user.role})")

        # Déterminer seller_id pour la suppression
        seller_id = current_user.id
        if current_user.role in ["admin", "vendeur"]:
            seller_id = "admin"  # Admin et vendeur peuvent supprimer tous les produits

        success, message = await product_service.delete_product(product_id, seller_id, current_user.role)

        if not success:
            logger.warning(f"Échec suppression produit {product_id}: {message}")
            # Déterminer le code d'erreur approprié selon le message
            if "non trouvé" in message.lower() or "invalide" in message.lower():
                status_code = 404
            elif "accès refusé" in message.lower() or "propres produits" in message.lower():
                status_code = 403
            elif "déjà supprimé" in message.lower():
                status_code = 400
            else:
                status_code = 400

            raise HTTPException(status_code=status_code, detail=message)

        logger.info(f"Produit supprimé avec succès: {product_id}")
        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression produit {product_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")

# === ROUTES CATÉGORIES ===

@router.get("/categories/", response_model=List[CategoryPublic])
async def get_categories(parent_id: Optional[str] = None, current_user: UserPublic = Depends(get_current_user)):
    """Récupère les catégories."""
    # Autoriser l'accès aux vendeurs et admins pour récupérer les catégories
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur/Admin requis")
    try:
        logger.info(f"Récupération catégories - parent_id: {parent_id} par {current_user.email}")
        categories = await product_service.get_categories(parent_id)
        logger.info(f"Catégories trouvées: {len(categories)}")
        return categories
    except Exception as e:
        logger.error(f"Erreur récupération catégories: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/categories/{category_id}", response_model=CategoryPublic)
async def get_category(category_id: str):
    """Récupère une catégorie par son ID."""
    try:
        logger.info(f"Récupération catégorie ID: {category_id}")
        category = await product_service.get_category(category_id)
        if not category:
            logger.warning(f"Catégorie non trouvée: {category_id}")
            raise HTTPException(status_code=404, detail="Catégorie non trouvée")
        return category
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération catégorie {category_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.post("/categories/", response_model=CategoryPublic)
async def create_category(
    category: CategoryCreate,
    current_user: UserPublic = Depends(get_current_user)
):
    """Crée une nouvelle catégorie (vendeur/admin uniquement)."""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur/Admin requis")

    try:
        logger.info(f"Création catégorie par {current_user.email}: {category.name}")
        new_category = await product_service.create_category(category)
        logger.info(f"Catégorie créée avec succès: {new_category.id}")
        return new_category
    except Exception as e:
        logger.error(f"Erreur création catégorie: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création: {str(e)}")

@router.put("/categories/{category_id}", response_model=CategoryPublic)
async def update_category(
    category_id: str,
    category_update: CategoryUpdate,
    current_user: UserPublic = Depends(get_current_user)
):
    """Met à jour une catégorie (vendeur/admin uniquement)."""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur/Admin requis")

    try:
        logger.info(f"Mise à jour catégorie {category_id} par {current_user.email}")
        updated_category = await product_service.update_category(category_id, category_update)
        if not updated_category:
            logger.warning(f"Catégorie non trouvée: {category_id}")
            raise HTTPException(status_code=404, detail="Catégorie non trouvée")

        logger.info(f"Catégorie mise à jour avec succès: {category_id}")
        return updated_category
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur mise à jour catégorie {category_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour: {str(e)}")

@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: str,
    current_user: UserPublic = Depends(get_current_user)
):
    """Supprime une catégorie (vendeur/admin uniquement)."""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Vendeur/Admin requis")

    try:
        logger.info(f"Suppression catégorie {category_id} par {current_user.email}")
        success = await product_service.delete_category(category_id)
        if not success:
            logger.warning(f"Catégorie non trouvée ou contient des produits: {category_id}")
            raise HTTPException(status_code=404, detail="Catégorie non trouvée ou contient des produits")

        logger.info(f"Catégorie supprimée avec succès: {category_id}")
        return {"message": "Catégorie supprimée avec succès"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression catégorie {category_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")
