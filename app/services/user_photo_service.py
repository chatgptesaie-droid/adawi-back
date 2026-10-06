from datetime import datetime
from typing import List, Optional
import asyncio
import cloudinary
import cloudinary.uploader
from app.db.mongo import db
from app.models.user_photo import UserPhotoCreate, UserPhotoInDB
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Configuration Cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

class UserPhotoService:
    def __init__(self):
        self.collection = db.user_photos

    async def upload_photos(self, photos: List[bytes], descriptions: List[str], user_id: str) -> List[UserPhotoInDB]:
        """Upload multiple photos to Cloudinary and save to database."""
        logger.info(f"Starting photo upload for user {user_id}, {len(photos)} photos")
        logger.info(f"Cloudinary config: cloud_name={settings.CLOUDINARY_CLOUD_NAME}, api_key={settings.CLOUDINARY_API_KEY[:10]}...")

        # Validate Cloudinary configuration
        if not settings.CLOUDINARY_CLOUD_NAME or not settings.CLOUDINARY_API_KEY or not settings.CLOUDINARY_API_SECRET:
            logger.error("Cloudinary configuration is missing. Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET environment variables.")
            raise Exception("Configuration Cloudinary manquante")

        uploaded_photos = []

        for i, (photo_data, description) in enumerate(zip(photos, descriptions)):
            logger.info(f"Processing photo {i+1}/{len(photos)}, size: {len(photo_data)} bytes")
            try:
                # Validate photo data is not empty
                if not photo_data or len(photo_data) == 0:
                    logger.error(f"Photo {i+1} has empty data")
                    continue

                # Upload to Cloudinary
                upload_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        cloudinary.uploader.upload,
                        photo_data,
                        folder="user-photos",
                        public_id=f"user-{user_id}-photo-{i}-{datetime.utcnow().timestamp()}",
                        overwrite=True,
                        resource_type="image",
                        quality="auto"
                    ),
                    timeout=300.0  # 5 minutes timeout
                )

                image_url = upload_result.get('secure_url')
                if not image_url:
                    logger.error(f"No secure_url in Cloudinary response for photo {i+1}")
                    continue

                logger.info(f"Photo uploadée vers Cloudinary: {image_url}")

                # Create photo record
                photo_create_data = UserPhotoCreate(
                    image_url=image_url,
                    description=description or "",
                    user_id=user_id
                )

                # Save to database
                db_photo = {
                    **photo_create_data.dict(),
                    "created_at": datetime.utcnow()
                }

                result = await self.collection.insert_one(db_photo)
                db_photo["_id"] = str(result.inserted_id)  # Set _id field as string (alias for id)

                logger.debug(f"db_photo before UserPhotoInDB: {db_photo}")

                try:
                    uploaded_photo = UserPhotoInDB(**db_photo)
                    uploaded_photos.append(uploaded_photo)
                    logger.info(f"Photo {i+1} successfully processed and saved")
                except Exception as e:
                    logger.error(f"Pydantic validation error for UserPhotoInDB: {e}")
                    raise

            except asyncio.TimeoutError:
                logger.error(f"Timeout upload Cloudinary pour photo {i+1} (5 minutes)")
                continue
            except cloudinary.exceptions.Error as e:
                logger.error(f"Cloudinary error for photo {i+1}: {str(e)}")
                continue
            except Exception as e:
                import traceback
                logger.error(f"Erreur upload photo {i+1}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

        logger.info(f"Upload completed: {len(uploaded_photos)}/{len(photos)} photos successfully uploaded")
        return uploaded_photos

    async def get_user_photos(self, user_id: str, skip: int = 0, limit: int = 100) -> List[UserPhotoInDB]:
        """Get photos uploaded by a specific user."""
        try:
            cursor = self.collection.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
            photos = []

            async for photo in cursor:
                photo["id"] = str(photo["_id"])
                del photo["_id"]
                photos.append(UserPhotoInDB(**photo))

            return photos
        except Exception as e:
            logger.error(f"Erreur récupération photos utilisateur {user_id}: {str(e)}")
            return []

    async def get_all_photos(self, skip: int = 0, limit: int = 100) -> List[UserPhotoInDB]:
        """Get all photos (for admin)."""
        try:
            cursor = self.collection.find({}).sort("created_at", -1).skip(skip).limit(limit)
            photos = []

            async for photo in cursor:
                # Keep _id as string for the model
                photo["_id"] = str(photo["_id"])
                photos.append(UserPhotoInDB(**photo))

            logger.info(f"Retrieved {len(photos)} photos from database")
            return photos
        except Exception as e:
            logger.error(f"Erreur récupération toutes les photos: {str(e)}")
            return []

    async def delete_photo(self, photo_id: str, user_id: str, is_admin_or_vendeur: bool = False) -> bool:
        """Delete a photo (only by the owner, admin, or vendeur)."""
        try:
            from bson import ObjectId
            if not ObjectId.is_valid(photo_id):
                return False

            # Check if photo exists
            photo = await self.collection.find_one({"_id": ObjectId(photo_id)})
            if not photo:
                return False

            # Allow deletion if user is owner, admin, or vendeur
            if photo["user_id"] == user_id or is_admin_or_vendeur:
                result = await self.collection.delete_one({"_id": ObjectId(photo_id)})
                return result.deleted_count > 0

            return False
        except Exception as e:
            logger.error(f"Erreur suppression photo {photo_id}: {str(e)}")
            return False

user_photo_service = UserPhotoService()
