import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class Settings:
    def __init__(self):
        self.MONGODB_URI = os.getenv(
            "MONGODB_URI",
            ""
            # "mongodb+srv://Marc:M9hoxdJ7eMFgsQNi@cluster0.1a2v0p5.mongodb.net/SHOWROOM?retryWrites=true&w=majority&appName=Cluster0"
        )
        self.MONGODB_DB = os.getenv("MONGODB_DB", "")
        self.JWT_SECRET = os.getenv("JWT_SECRET", "")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "")
        self.ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", ""))
        self.SMTP_HOST = os.getenv("SMTP_HOST", "")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", ""))
        self.SMTP_USER = os.getenv("SMTP_USER", "")
        self.SMTP_PASS = os.getenv("SMTP_PASS", "")
        self.FRONTEND_URL = os.getenv("FRONTEND_URL", "")
        self.API_KEY_PAYGATE = os.getenv("API_KEY_PAYGATE", "")
        self.API_KEY_MONEYFUSION = os.getenv("API_KEY_MONEYFUSION", "test_moneyfusion_key")
        self.RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
        self.DOMAIN_EMAIL = os.getenv("DOMAIN_EMAIL", "onboarding@resend.dev")

        
        # Cloudinary configuration
        self.CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        self.CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
        self.CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
        
        print(f"✅ Configuration chargée:")
        print(f"   MongoDB URI: {self.MONGODB_URI[:50]}...")
        print(f"   MongoDB DB: {self.MONGODB_DB}")
        print(f"   Frontend URL: {self.FRONTEND_URL}")
        print(f"   PayGate API Key: {'Configured' if self.API_KEY_PAYGATE != 'test_paygate_key' else 'Test mode'}")
        print(f"   MoneyFusion API Key: {'Configured' if self.API_KEY_MONEYFUSION != 'test_moneyfusion_key' else 'Test mode'}")

settings = Settings()
