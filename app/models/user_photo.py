from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId

class UserPhotoBase(BaseModel):
    image_url: str = Field(..., description="URL de l'image uploadée")
    description: Optional[str] = Field(None, description="Description de la photo")

class UserPhotoCreate(UserPhotoBase):
    user_id: str = Field(..., description="ID de l'utilisateur qui a uploadé la photo")

class UserPhotoInDB(UserPhotoBase):
    id: str = Field(..., alias="_id")
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat(),
        }
