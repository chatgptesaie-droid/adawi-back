from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from datetime import datetime
from bson import ObjectId
from app.models.cart import CartItem, CartPublic, UpdateQuantityRequest, QuantityChangeRequest, BatchUpdateRequest
from app.services.cart_service import cart_service
from app.api.auth import get_current_user_optional as get_current_user
from app.models.user import UserPublic

router = APIRouter(prefix="/cart", tags=["cart"])

def calculate_cart_total(items):
    return sum((item.price or 0) * item.quantity for item in items)

async def validate_product_id(product_id: str) -> bool:
    """Valide qu'un product_id est un ObjectId MongoDB valide et que le produit existe"""
    if not product_id or not isinstance(product_id, str):
        return False
    # Vérifier que c'est une chaîne de 24 caractères hexadécimaux
    if len(product_id) != 24 or not all(c in '0123456789abcdefABCDEF' for c in product_id):
        return False

    # Vérifier que le produit existe en base
    from app.services.product_service import product_service
    product = await product_service.get_product(product_id)
    return product is not None

# Récupérer le panier courant (user_id ou session_id)
@router.get("/", response_model=CartPublic)
async def get_cart(
    # action: Optional[str] = None,  # "increase" ou "decrease"
    # product_id: Optional[str] = None,
    # size: Optional[str] = None,
    # color: Optional[str] = None,
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    user_id = current_user.id if current_user else None
    cart = await cart_service.get_cart(user_id=user_id, session_id=session_id)
    if not cart:
        cart = await cart_service.create_cart(user_id=user_id, session_id=session_id)

    # # Gérer les actions d'augmentation/diminution si demandées
    # if action and product_id:
    #     if action not in ["increase", "decrease"]:
    #         raise HTTPException(status_code=400, detail="Action doit être 'increase' ou 'decrease'")

    #     # Chercher l'item dans le panier
    #     found = False
    #     for item in cart.items:
    #         product_match = item.product_id == product_id
    #         size_match = (size is None and item.size is None) or (size is not None and item.size == size)
    #         color_match = (color is None and item.color is None) or (color is not None and item.color == color)

    #         if product_match and size_match and color_match:
    #             if action == "increase":
    #                 item.quantity += 1
    #             elif action == "decrease":
    #                 if item.quantity > 1:
    #                     item.quantity -= 1
    #                 else:
    #                     raise HTTPException(status_code=400, detail="La quantité ne peut pas être inférieure à 1. Utilisez la suppression pour retirer le produit.")
    #             found = True
    #             break

    #     if not found:
    #         raise HTTPException(status_code=404, detail="Produit non trouvé dans le panier")

    #     # Mettre à jour en base
    #     await cart_service.collection.update_one(
    #         {"_id": cart.id},
    #         {"$set": {"items": [i.dict() for i in cart.items], "updated_at": datetime.utcnow()}}
    #     )

    #     # Récupérer le panier mis à jour
    #     cart = await cart_service.get_cart(user_id=user_id, session_id=session_id)

    total = calculate_cart_total(cart.items)
    item_count = sum(item.quantity for item in cart.items)
    cart_dict = cart.dict()
    cart_dict["total"] = total
    cart_dict["item_count"] = item_count
    return CartPublic(**cart_dict)

# Ajouter ou modifier un item dans le panier
@router.post("/add", response_model=CartPublic)
async def add_or_update_item(
    item: CartItem,
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    # Validation du product_id avant traitement
    if not await validate_product_id(item.product_id):
        raise HTTPException(
            status_code=400,
            detail=f"product_id invalide ou produit inexistant: '{item.product_id}'. Doit être un ObjectId MongoDB valide et le produit doit exister."
        )

    user_id = current_user.id if current_user else None
    cart = await cart_service.add_or_update_item(item, user_id=user_id, session_id=session_id)
    total = calculate_cart_total(cart.items)
    item_count = sum(item.quantity for item in cart.items)
    cart_dict = cart.dict()
    cart_dict["total"] = total
    cart_dict["item_count"] = item_count
    return CartPublic(**cart_dict)

# Supprimer un item du panier
@router.delete("/remove/{product_id}", response_model=CartPublic)
async def remove_item(
    product_id: str,
    size: Optional[str] = None,
    color: Optional[str] = None,
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    try:
        # Validation du product_id
        if not await validate_product_id(product_id):
            raise HTTPException(status_code=400, detail=f"product_id invalide ou produit inexistant: '{product_id}'")

        user_id = current_user.id if current_user else None
        cart = await cart_service.remove_item(product_id, size, color, user_id, session_id)
        total = calculate_cart_total(cart.items)
        item_count = sum(item.quantity for item in cart.items)
        cart_dict = cart.dict()
        cart_dict["total"] = total
        cart_dict["item_count"] = item_count
        return CartPublic(**cart_dict)
    except Exception as e:
        print(f"Error in remove_item: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Mettre à jour la quantité d'un item dans le panier
@router.put("/update_quantity", response_model=CartPublic)
async def update_item_quantity(
    request: UpdateQuantityRequest,
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    try:
        # Validation du product_id
        if not await validate_product_id(request.product_id):
            raise HTTPException(status_code=400, detail=f"product_id invalide ou produit inexistant: '{request.product_id}'")

        user_id = current_user.id if current_user else None
        cart = await cart_service.update_item_quantity(request.product_id, request.quantity, request.size, request.color, user_id, session_id)
        total = calculate_cart_total(cart.items)
        item_count = sum(item.quantity for item in cart.items)
        cart_dict = cart.dict()
        cart_dict["total"] = total
        cart_dict["item_count"] = item_count
        return CartPublic(**cart_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error in update_item_quantity: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Augmenter la quantité d'un item
@router.post("/increase_quantity", response_model=CartPublic)
async def increase_quantity(
    request: QuantityChangeRequest,
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    try:
        # Validation du product_id
        if not await validate_product_id(request.product_id):
            raise HTTPException(status_code=400, detail=f"product_id invalide ou produit inexistant: '{request.product_id}'")

        user_id = current_user.id if current_user else None
        cart = await cart_service.increase_item(request.product_id, request.size, request.color, user_id, session_id)
        total = calculate_cart_total(cart.items)
        item_count = sum(item.quantity for item in cart.items)
        cart_dict = cart.dict()
        cart_dict["total"] = total
        cart_dict["item_count"] = item_count
        return CartPublic(**cart_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error in increase_quantity: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Diminuer la quantité d'un item
@router.post("/decrease_quantity", response_model=CartPublic)
async def decrease_quantity(
    request: QuantityChangeRequest,
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    try:
        # Validation du product_id
        if not await validate_product_id(request.product_id):
            raise HTTPException(status_code=400, detail=f"product_id invalide ou produit inexistant: '{request.product_id}'")

        user_id = current_user.id if current_user else None
        cart = await cart_service.decrease_item(request.product_id, request.size, request.color, user_id, session_id)
        total = calculate_cart_total(cart.items)
        item_count = sum(item.quantity for item in cart.items)
        cart_dict = cart.dict()
        cart_dict["total"] = total
        cart_dict["item_count"] = item_count
        return CartPublic(**cart_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error in decrease_quantity: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Mise à jour par lot d'items dans le panier
@router.post("/batch_update", response_model=CartPublic)
async def batch_update_items(
    request: BatchUpdateRequest,
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    try:
        user_id = current_user.id if current_user else None
        cart = await cart_service.batch_update(request.updates, user_id=user_id, session_id=session_id)
        total = calculate_cart_total(cart.items)
        item_count = sum(item.quantity for item in cart.items)
        cart_dict = cart.dict()
        cart_dict["total"] = total
        cart_dict["item_count"] = item_count
        return CartPublic(**cart_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error in batch_update_items: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Vider le panier
@router.delete("/clear", response_model=CartPublic)
async def clear_cart(
    session_id: Optional[str] = Header(None),
    current_user: Optional[UserPublic] = Depends(get_current_user)
):
    user_id = current_user.id if current_user else None
    cart = await cart_service.clear_cart(user_id=user_id, session_id=session_id)
    total = calculate_cart_total(cart.items)
    item_count = sum(item.quantity for item in cart.items)
    cart_dict = cart.dict()
    cart_dict["total"] = total
    cart_dict["item_count"] = item_count
    return CartPublic(**cart_dict)

# === ADMIN/VENDOR ENDPOINTS FOR MANAGING OTHER USERS' CARTS ===

# @router.get("/admin/user/{user_id}", response_model=CartPublic)
# async def get_user_cart_admin(
#     user_id: str,
#     current_user: UserPublic = Depends(get_current_user)
# ):
#     """
#     Récupère le panier d'un utilisateur spécifique (admin/vendeur seulement)
#     """
#     if current_user.role == "client":
#         raise HTTPException(status_code=403, detail="Accès non autorisé")

#     cart = await cart_service.get_cart(user_id=user_id)
#     if not cart:
#         cart = await cart_service.create_cart(user_id=user_id)

#     total = calculate_cart_total(cart.items)
#     item_count = sum(item.quantity for item in cart.items)
#     cart_dict = cart.dict()
#     cart_dict["total"] = total
#     cart_dict["item_count"] = item_count
#     return CartPublic(**cart_dict)

# @router.post("/admin/user/{user_id}/add", response_model=CartPublic)
# async def add_item_to_user_cart_admin(
#     user_id: str,
#     item: CartItem,
#     current_user: UserPublic = Depends(get_current_user)
# ):
#     """
#     Ajoute un item au panier d'un utilisateur spécifique (admin/vendeur seulement)
#     """
#     if current_user.role == "client":
#         raise HTTPException(status_code=403, detail="Accès non autorisé")

#     # Validation du product_id avant traitement
#     if not await validate_product_id(item.product_id):
#         raise HTTPException(
#             status_code=400,
#             detail=f"product_id invalide ou produit inexistant: '{item.product_id}'. Doit être un ObjectId MongoDB valide et le produit doit exister."
#         )

#     cart = await cart_service.add_or_update_item(item, user_id=user_id, session_id=None)
#     total = calculate_cart_total(cart.items)
#     item_count = sum(item.quantity for item in cart.items)
#     cart_dict = cart.dict()
#     cart_dict["total"] = total
#     cart_dict["item_count"] = item_count
#     return CartPublic(**cart_dict)

# @router.delete("/admin/user/{user_id}/remove/{product_id}", response_model=CartPublic)
# async def remove_item_from_user_cart_admin(
#     user_id: str,
#     product_id: str,
#     size: Optional[str] = None,
#     color: Optional[str] = None,
#     current_user: UserPublic = Depends(get_current_user)
# ):
#     """
#     Supprime un item du panier d'un utilisateur spécifique (admin/vendeur seulement)
#     """
#     if current_user.role == "client":
#         raise HTTPException(status_code=403, detail="Accès non autorisé")

#     try:
#         # Validation du product_id
#         if not await validate_product_id(product_id):
#             raise HTTPException(status_code=400, detail=f"product_id invalide ou produit inexistant: '{product_id}'")

#         cart = await cart_service.remove_item(product_id, size, color, user_id, None)
#         total = calculate_cart_total(cart.items)
#         item_count = sum(item.quantity for item in cart.items)
#         cart_dict = cart.dict()
#         cart_dict["total"] = total
#         cart_dict["item_count"] = item_count
#         return CartPublic(**cart_dict)
#     except Exception as e:
#         print(f"Error in remove_item_from_user_cart_admin: {e}")
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=str(e))

# @router.delete("/admin/user/{user_id}/clear", response_model=CartPublic)
# async def clear_user_cart_admin(
#     user_id: str,
#     current_user: UserPublic = Depends(get_current_user)
# ):
#     """
#     Vide le panier d'un utilisateur spécifique (admin/vendeur seulement)
#     """
#     if current_user.role == "client":
#         raise HTTPException(status_code=403, detail="Accès non autorisé")

#     cart = await cart_service.clear_cart(user_id=user_id, session_id=None)
#     total = calculate_cart_total(cart.items)
#     item_count = sum(item.quantity for item in cart.items)
#     cart_dict = cart.dict()
#     cart_dict["total"] = total
#     cart_dict["item_count"] = item_count
#     return CartPublic(**cart_dict)
