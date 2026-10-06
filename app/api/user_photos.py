from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from typing import List, Optional
from app.models.user_photo import UserPhotoInDB
from app.services.user_photo_service import user_photo_service
from app.api.auth import get_current_user
from app.models.user import UserPublic
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-photos", tags=["user-photos"])

@router.post("/", response_model=List[UserPhotoInDB])
async def upload_photos(
    photos: List[UploadFile] = File(...),
    descriptions: Optional[str] = Form(None),  # JSON string of descriptions array (optional)
    current_user: UserPublic = Depends(get_current_user)
):
    """Upload up to 10 photos with descriptions (admin/vendeur only)."""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Admin/Vendeur requis")

    try:
        # Validate number of photos
        if len(photos) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 photos autorisées")

        if len(photos) == 0:
            raise HTTPException(status_code=400, detail="Au moins une photo requise")

        # Parse descriptions or generate defaults
        descriptions_list = []
        if descriptions and descriptions.strip():
            try:
                import json
                descriptions_list = json.loads(descriptions)
                if not isinstance(descriptions_list, list):
                    raise ValueError("Descriptions doit être une liste")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Invalid descriptions format: {str(e)}, generating defaults")
                # Generate default descriptions in French
                descriptions_list = [f"Photo d'accueil {i+1}" for i in range(len(photos))]
        else:
            # Generate default descriptions in French
            descriptions_list = [f"Photo d'accueil {i+1}" for i in range(len(photos))]

        # Validate descriptions length matches photos
        if len(descriptions_list) != len(photos):
            raise HTTPException(status_code=400, detail="Nombre de descriptions doit correspondre au nombre de photos")

        # Validate file types
        for photo in photos:
            if not photo.content_type or not photo.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail=f"Type de fichier non supporté: {photo.filename}")

        # Read photo data
        photo_data_list = []
        for photo in photos:
            contents = await photo.read()
            photo_data_list.append(contents)

        # Upload photos
        uploaded_photos = await user_photo_service.upload_photos(
            photo_data_list,
            descriptions_list,
            current_user.id
        )

        if not uploaded_photos:
            raise HTTPException(status_code=500, detail="Échec de l'upload des photos")

        logger.info(f"Photos uploadées avec succès par {current_user.email}: {len(uploaded_photos)} photos")
        return uploaded_photos

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur upload photos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload: {str(e)}")

@router.get("/", response_model=List[UserPhotoInDB])
async def get_photos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get photos (public access - photos are public)."""
    try:
        photos = await user_photo_service.get_all_photos(skip=skip, limit=limit)
        return photos
    except Exception as e:
        logger.error(f"Erreur récupération photos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/admin/all", response_model=List[UserPhotoInDB])
async def get_all_photos_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserPublic = Depends(get_current_user)
):
    """Get all photos for admin/vendeur (for CRUD operations)."""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Admin/Vendeur requis")

    try:
        photos = await user_photo_service.get_all_photos(skip=skip, limit=limit)
        return photos
    except Exception as e:
        logger.error(f"Erreur récupération toutes les photos admin: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.get("/my-photos", response_model=List[UserPhotoInDB])
async def get_my_photos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserPublic = Depends(get_current_user)
):
    """Get current user's photos."""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Admin/Vendeur requis")

    try:
        photos = await user_photo_service.get_user_photos(current_user.id, skip=skip, limit=limit)
        return photos
    except Exception as e:
        logger.error(f"Erreur récupération photos utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@router.delete("/{photo_id}")
async def delete_photo(
    photo_id: str,
    current_user: UserPublic = Depends(get_current_user)
):
    """Delete a photo (owner or admin only)."""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé - Admin/Vendeur requis")

    try:
        is_admin_or_vendeur = current_user.role in ["admin", "vendeur"]
        success = await user_photo_service.delete_photo(photo_id, current_user.id, is_admin_or_vendeur)
        if not success:
            raise HTTPException(status_code=404, detail="Photo non trouvée ou accès refusé")

        return {"message": "Photo supprimée avec succès"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression photo {photo_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")
