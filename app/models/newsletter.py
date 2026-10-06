from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class NewsletterSubscriber(BaseModel):
    id: Optional[str]
    name: str
    email: EmailStr
    subscribed_at: datetime
