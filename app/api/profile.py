from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional, List
from app.models.user import UserPublic, UserInDB
from app.models.order import Measurements, Address
from app.models.product import ProductSize
from app.services.user_service import user_service
from app.api.auth import get_current_user
import cloudinary.uploader
import json
from app.core.config import settings

router = APIRouter(prefix="/profile", tags=["profile"])

@router.get("/", response_model=UserPublic)
async def get_my_profile(current_user: UserPublic = Depends(get_current_user)):
    """Récupérer son propre profil utilisateur."""
    user = await user_service.get_user_by_id(current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return UserPublic(**user.dict())

@router.put("/", response_model=UserPublic)
async def update_my_profile(
    measurements: Optional[str] = Form(None),
    size: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    photos: List[UploadFile] = File(None),
    current_user: UserPublic = Depends(get_current_user)
):
    """Mettre à jour son propre profil (mesures, taille, photos) - réservé aux clients."""
    if current_user.role != "client":
        raise HTTPException(status_code=403, detail="Accès réservé aux clients")

    # Parser les mesures si fournies
    measurements_obj = None
    if measurements:
        try:
            measurements_data = json.loads(measurements)
            measurements_obj = Measurements(**measurements_data)
        except:
            raise HTTPException(status_code=400, detail="Format des mesures invalide")

    # Parser la taille
    size_obj = None
    if size:
        try:
            size_obj = ProductSize(size)
        except:
            raise HTTPException(status_code=400, detail="Taille invalide")

    # Parser l'adresse si fournie
    address_obj = None
    if address:
        try:
            address_data = json.loads(address)
            address_obj = Address(**address_data)
        except:
            raise HTTPException(status_code=400, detail="Format de l'adresse invalide")

    # Gérer l'upload des photos
    photo_urls = []
    if photos:
        for photo in photos[:5]:  # Limiter à 5 photos
            if photo.filename:
                try:
                    # Upload vers Cloudinary
                    upload_result = cloudinary.uploader.upload(
                        photo.file,
                        folder="user_profiles",
                        public_id=f"user_{current_user.id}_{photo.filename}",
                        resource_type="image"
                    )
                    photo_urls.append(upload_result["secure_url"])
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Erreur upload photo: {str(e)}")

    # Mettre à jour le profil
    user = await user_service.update_user_profile(
        user_id=current_user.id,
        measurements=measurements_obj,
        size=size_obj,
        address=address_obj,
        photo=photo_urls if photo_urls else None
    )
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user
