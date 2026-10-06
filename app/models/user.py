from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from app.models.order import Measurements, Address
from app.models.product import ProductSize

# les fichiers a corriger commence par model>user.py, core>auth.py et api>auth.py 
# A decommenter si on utilise UserRole
# class UserRole(str, Enum):
#     CLIENT = "client"
#     VENDEUR = "vendeur"
#     ADMIN = "admin"
  
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: str = "client"    # A commenter si on utilise UserRole
    # roles: Set[UserRole] = {UserRole.CLIENT}  # Nouveau champ
    is_banned: bool = False
    is_active: bool = True
    is_deleted: bool = False
    measurements: Optional[Measurements] = None
    size: Optional[ProductSize] = None
    address: Optional[Address] = None
    photo: Optional[List[str]] = []

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserInDB(UserBase):
    id: str
    hashed_password: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    failed_login_attempts: int = 0  # Nombre d'essais échoués
    locked_until: Optional[datetime] = None  # Date/heure jusqu'à laquelle le compte est verrouillé

class UserPublic(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer" 
    session_id: str 


class TokenData(BaseModel):
    email: Optional[str] = None