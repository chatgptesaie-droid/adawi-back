from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List
from app.models.user import UserPublic
from app.services.user_service import user_service
from app.core.security import verify_token

security = HTTPBearer()

# VERSION 1
# async def get_current_user(credentials = Depends(security)) -> UserPublic:

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserPublic:
    """Récupère les informations de l'utilisateur connecté."""
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token invalide")

    email = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=401, detail="Token invalide")

    user = await user_service.get_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")

    return UserPublic(**user.dict())


# La fonction retourne une dépendance, 
# mais son nom suggère qu'elle vérifie juste les rôles. 
# Elle fait AUSSI toute l'authentification.
def require_roles(allowed_roles: List[str]):
    """Dépendance pour vérifier que l'utilisateur a l'un des rôles autorisés."""
    async def role_checker(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserPublic:
        token = credentials.credentials
        payload = verify_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Token invalide")

        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Token invalide")

        user = await user_service.get_user_by_email(email)
        if user is None:
            raise HTTPException(status_code=401, detail="Utilisateur non trouvé")

        # Vérifier si l'utilisateur a l'un des rôles autorisés
        user_roles = user.get("roles", [])
        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Accès refusé. Rôles requis: {', '.join(allowed_roles)}"
            )

        return UserPublic(**user.dict())

    return role_checker



# async def get_current_user(
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ) -> UserPublic:
#     """Dépendance de base : utilisateur connecté"""
#     # ... récupération user ...

# def require_roles(allowed_roles: List[str]):
#     """Dépendance qui combine authentification + rôles"""
#     async def role_checker(
#         current_user: UserPublic = Depends(get_current_user)  # ✅ RÉUTILISATION !
#     ) -> UserPublic:
#         # Plus besoin de refaire l'auth, on a déjà current_user
        
#         # Vérification des rôles (adapté au modèle UserBase)
#         if current_user.role not in allowed_roles:  # ✅ Cohérent avec UserBase
#             raise HTTPException(
#                 status_code=403,
#                 detail=f"Rôle requis: {', '.join(allowed_roles)}"
#             )
#         return current_user
#     return role_checker

# # app/api/orders.py
# @router.put("/{order_id}/status", response_model=OrderPublic)
# async def update_status(
#     order_id: str,
#     status: OrderStatus,
#     comment: Optional[str] = None,
#     current_user: UserPublic = Depends(require_roles(["admin", "vendeur"]))  # ✅ Propre !
# ):
#     # Plus de if current_user.role... ici !
#     # La permission est déjà vérifiée par la dépendance
    
#     # Juste la logique métier
#     order = await order_service.get_order(order_id)
#     # ... reste du code
