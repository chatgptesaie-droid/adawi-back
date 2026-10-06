from pydantic_settings import BaseSettings
from pydantic import ConfigDict
import os
from dotenv import load_dotenv

# Charger le fichier .env explicitement
load_dotenv()

class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra='ignore'
    )
    
    # Variables MongoDB
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("MONGODB_DB", "showroom")
    
    # Variables JWT
    jwt_secret: str = os.getenv("JWT_SECRET", "supersecretkey123456789")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    
    # Variables SMTP
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")

# Créer l'instance
settings = Settings()

# Debugging
print(f"🔍 Configuration chargée:")
print(f"   MongoDB URI: {settings.mongodb_uri[:50]}...")
print(f"   MongoDB DB: {settings.mongodb_db}")
print(f"   JWT Secret: {settings.jwt_secret[:10]}...")
