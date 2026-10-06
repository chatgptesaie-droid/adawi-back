import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from bson import ObjectId
import cloudinary
import cloudinary.uploader
from app.db.mongo import db
from app.models.user import UserCreate, UserInDB, UserPublic
from app.core.security import get_password_hash, verify_password
from app.core.config import settings
from pymongo.errors import OperationFailure

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

class UserService:
    def __init__(self):
        self.collection = db.users

    async def create_user(self, user: UserCreate) -> UserPublic:
        """Crée un nouvel utilisateur."""
        from pymongo.errors import OperationFailure
        # Vérifier si l'email existe déjà
        existing_user = await self.collection.find_one({"email": user.email})
        if existing_user:
            raise ValueError("Un utilisateur avec cet email existe déjà")

        photo_urls = []
        for photo in user.photo or []:
            if not photo.startswith("data:image/"):
                photo_urls.append(photo)
                continue

            if not all((
                settings.CLOUDINARY_CLOUD_NAME,
                settings.CLOUDINARY_API_KEY,
                settings.CLOUDINARY_API_SECRET
            )):
                raise ValueError("Configuration Cloudinary manquante pour téléverser la photo")

            try:
                upload_result = await asyncio.to_thread(
                    cloudinary.uploader.upload,
                    photo,
                    folder="user_profiles",
                    public_id=f"user-{uuid.uuid4().hex}",
                    resource_type="image"
                )
                photo_url = upload_result.get("secure_url")
                if not photo_url:
                    raise ValueError("Cloudinary n'a pas retourné l'URL de la photo")
                photo_urls.append(photo_url)
            except Exception as error:
                raise ValueError("Échec du téléversement de la photo vers Cloudinary") from error
        
        # Créer l'utilisateur
        now = datetime.utcnow()
        user_data = {
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "hashed_password": get_password_hash(user.password),
            "is_banned": user.is_banned,
            "is_active": user.is_active,
            "is_deleted": user.is_deleted,
            "measurements": user.measurements.dict() if user.measurements else {
                "height": 0,
                "weight": 0,
                "shoulder_width": 0,
                "chest": 0,
                "waist_length": 0,
                "ventral_circumference": 0,
                "hips": 0,
                "corsage_length": 0,
                "belt": 0,
                "skirt_length": 0,
                "dress_length": 0,
                "sleeve_length": 0,
                "sleeve_circumference": 0,
                "pants_length": 0,
                "short_dress_length": 0,
                "thigh_circumference": 0,
                "knee_length": 0,
                "knee_circumference": 0,
                "bottom": 0,
                "inseam": 0,
                "other_measurements": None
            },
            "size": user.size.value if user.size else None,
            "address": user.address.dict() if user.address else None,
            "photo": photo_urls,
            "created_at": now,
            "updated_at": now
        }
        try:
            result = await self.collection.insert_one(user_data)
            user_data["id"] = str(result.inserted_id)
        except OperationFailure as e:
            raise ValueError("Erreur de permission MongoDB: impossible de créer l'utilisateur. Veuillez vérifier les permissions de la base de données.")
        
        return UserPublic(**user_data)

    async def authenticate_user(self, email: str, password: str) -> Optional[UserInDB]:
        """Authentifie un utilisateur."""
        user = await self.collection.find_one({"email": email})
        if not user:
            return None
        
        if user.get("is_banned"):
            return None
        
        # Vérifier si le compte est verrouillé
        locked_until = user.get("locked_until")
        if locked_until and locked_until > datetime.utcnow():
            # Le compte est verrouillé, on retourne None
            return None
        
        # Si le compte était verrouillé mais la période est expirée, réinitialiser
        if locked_until and locked_until <= datetime.utcnow():
            await self.collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"failed_login_attempts": 0, "locked_until": None}}
            )
            user["failed_login_attempts"] = 0
            user["locked_until"] = None
        
        # D'abord vérifier le mot de passe
        if verify_password(password, user["hashed_password"]):
            # Réinitialiser les compteurs en cas de connexion réussie
            await self.collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"failed_login_attempts": 0, "locked_until": None}}
            )
            
            user["id"] = str(user["_id"])
            return UserInDB(**user)
        else:
            # Incrémenter le compteur d'échecs
            failed_attempts = user.get("failed_login_attempts", 0) + 1
            
            # Si 3 échecs ou plus, verrouiller le compte pendant 15 minutes
            if failed_attempts >= 3:
                locked_until = datetime.utcnow() + timedelta(minutes=15)
                update_data = {
                    "$set": {
                        "failed_login_attempts": 0,  # Réinitialiser après verrouillage
                        "locked_until": locked_until,
                        "last_failed_attempt": datetime.utcnow()
                    }
                }
            else:
                update_data = {
                    "$inc": {"failed_login_attempts": 1},
                    "$set": {"last_failed_attempt": datetime.utcnow()}
                }
            
            await self.collection.update_one(
                {"_id": user["_id"]},
                update_data
            )
            return None

    async def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        """Récupère un utilisateur par son email."""
        user = await self.collection.find_one({"email": email})
        if not user:
            return None
        
        user["id"] = str(user["_id"])
        return UserInDB(**user)

    async def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        """Récupère un utilisateur par son ID."""
        try:
            user = await self.collection.find_one({"_id": ObjectId(user_id)})
            if not user:
                return None

            user["id"] = str(user["_id"])
            return UserInDB(**user)
        except:
            return None

    async def get_user_public_by_id(self, user_id: str) -> Optional[UserPublic]:
        """Récupère un utilisateur public par son ID."""
        try:
            user = await self.collection.find_one({"_id": ObjectId(user_id)})
            if not user:
                return None

            user["id"] = str(user["_id"])
            return UserPublic(**user)
        except:
            return None

    async def list_users(self, role: Optional[str] = None, q: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[UserPublic]:
        """Liste les utilisateurs avec des options de filtrage."""
        query = {}
        if role:
            query["role"] = role
        if q:
            query["$or"] = [
                {"email": {"$regex": q, "$options": "i"}},
                {"full_name": {"$regex": q, "$options": "i"}}
            ]
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        users: List[UserPublic] = []
        async for u in cursor:
            u["id"] = str(u["_id"])
            users.append(UserPublic(**u))
        return users

    async def ban_user(self, user_id: str, ban: bool) -> Optional[UserPublic]:
        """Bannir ou débannir un utilisateur."""
        res = await self.collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_banned": ban, "updated_at": datetime.utcnow()}})
        if res.modified_count:
            user = await self.collection.find_one({"_id": ObjectId(user_id)})
            user["id"] = str(user["_id"])
            return UserPublic(**user)
        return None

    async def update_role(self, user_id: str, role: str) -> Optional[UserPublic]:
        """Met à jour le rôle d'un utilisateur."""
        res = await self.collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": role, "updated_at": datetime.utcnow()}})
        if res.modified_count:
            user = await self.collection.find_one({"_id": ObjectId(user_id)})
            user["id"] = str(user["_id"])
            return UserPublic(**user)
        return None

    async def delete_user(self, user_id: str) -> bool:
        """Soft delete: marque l'utilisateur supprimé sans effacer ses données."""
        from datetime import datetime
        res = await self.collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_deleted": True, "is_active": False, "updated_at": datetime.utcnow(), "deleted_at": datetime.utcnow()}})
        return res.modified_count == 1

    async def update_user_profile(self, user_id: str, measurements=None, size=None, address=None, photo=None) -> Optional[UserPublic]:
        """Met à jour le profil utilisateur (mesures, taille, adresse, photo)."""
        update_data = {}
        if measurements is not None:
            update_data["measurements"] = measurements.dict() if measurements else None
        if size is not None:
            update_data["size"] = size.value if size else None
        if address is not None:
            update_data["address"] = address.dict() if address else None
        if photo is not None:
            update_data["photo"] = photo
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            res = await self.collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
            if res.modified_count:
                user = await self.collection.find_one({"_id": ObjectId(user_id)})
                user["id"] = str(user["_id"])
                return UserPublic(**user)
        return None

user_service = UserService()
