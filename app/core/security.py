from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings
import uuid

# Configuration pour le hashage des mots de passe
# Sans bcrypt externe, passlib utilise automatiquement le backend builtin
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# ____________________________________________________________ 

# verify_password() : À la CONNEXION pour vérifier
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si le mot de passe en clair correspond au hash."""
    # Truncate password to 72 bytes as per bcrypt limitation
    truncated_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(truncated_password, hashed_password)
# ____________________________________________________________   

# get_password_hash() : À l'INSCRIPTION quand tu sauvegardes le mot de passe
def get_password_hash(password: str) -> str:
    """Hash un mot de passe."""
    # Truncate password to 72 bytes as per bcrypt limitation
    truncated_password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(truncated_password)
# ____________________________________________________________
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Crée un token JWT d'accès."""
    # D'abord copier les données
    to_encode = data.copy()
    
    # Puis générer un session ID unique et l'ajouter
    session_id = str(uuid.uuid4())
    to_encode.update({"session_id": session_id})

    # Calculer l'expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Ajouter l'expiration au payload
    to_encode.update({"exp": int(expire.timestamp())})
    
    # Encoder le JWT
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    
    return encoded_jwt, session_id
# ____________________________________________________________
def verify_token(token: str) -> Optional[dict]:
    """Vérifie et décode un token JWT."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None