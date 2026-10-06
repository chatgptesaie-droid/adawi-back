import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class Settings:
    def __init__(self):
        self.MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.MONGODB_DB = os.getenv("MONGODB_DB", "showroom")
        self.JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey123456789")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
        self.SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.SMTP_USER = os.getenv("SMTP_USER", "")
        self.SMTP_PASS = os.getenv("SMTP_PASS", "")
        
        print(f"✅ Configuration chargée:")
        print(f"   MongoDB URI: {self.MONGODB_URI[:50]}...")
        print(f"   MongoDB DB: {self.MONGODB_DB}")

settings = Settings()
