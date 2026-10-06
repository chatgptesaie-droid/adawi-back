from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra='ignore'
    )
    
    # Variables MongoDB
    MONGODB_URI: str
    MONGODB_DB: str
    
    # Variables JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # Variables SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_USER: str = ""
    SMTP_PASS: str = ""

# Créer l'instance
settings = Settings()

# Debugging
print(f"🔍 Configuration chargée:")
print(f"   MongoDB URI: {settings.MONGODB_URI[:50]}...")
print(f"   MongoDB DB: {settings.MONGODB_DB}")
print(f"   JWT Secret: {settings.JWT_SECRET[:10]}...")
