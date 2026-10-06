# Documentation de la couche Infrastructure Layer

Cette couche est essentielle pour la gestion des aspects techniques bas niveau du backend, notamment la connexion à la base de données, la configuration centralisée, la sécurité (authentification, hashage), ainsi que la gestion du cache et des sessions.

---

## 1. Connexion MongoDB (Motor)

- Fichier principal : `backend/app/db/mongo.py`
- Utilisation de Motor, un client MongoDB asynchrone pour Python.
- La connexion est établie via `AsyncIOMotorClient` avec l'URI MongoDB récupéré depuis la configuration centralisée.
- La base de données est sélectionnée via `client[settings.MONGODB_DB]`.
- Une fonction `ensure_indexes` crée les index nécessaires pour optimiser les requêtes et la sécurité.
- La fonction `init_db` initialise la base de données et crée les index au démarrage de l'application.

---

## 2. Configuration Centralisée

- Fichier principal : `backend/app/core/config.py`
- Utilisation de la bibliothèque `python-dotenv` pour charger les variables d'environnement depuis un fichier `.env`.
- Classe `Settings` qui centralise toutes les configurations importantes :
  - URI MongoDB, nom de la base
  - Clé secrète JWT, algorithme, durée d'expiration
  - Configuration SMTP pour l'envoi d'emails
  - Clés API pour les intégrations externes (PayGate, MoneyFusion)
- Instance globale `settings` utilisée dans toute l'application pour accéder aux configurations.

---

## 3. Sécurité (JWT, Hashage)

- Fichier principal : `backend/app/core/security.py`
- Hashage des mots de passe avec `passlib` et l'algorithme bcrypt.
- Fonctions pour hasher un mot de passe (`get_password_hash`) et vérifier un mot de passe (`verify_password`).
- Création de tokens JWT avec la bibliothèque `python-jose` :
  - `create_access_token` génère un token JWT avec un payload personnalisé, une expiration, et un identifiant de session unique.
  - `verify_token` décode et valide un token JWT, retourne le payload ou None si invalide.
- Ces fonctions sont utilisées dans les endpoints d'authentification pour sécuriser l'accès.

---

## 4. Cache et Sessions

- La documentation et le code source ne montrent pas explicitement l'implémentation d'un cache ou gestion de sessions.
- Possibilité d'utilisation future de Redis ou autre solution pour la gestion des sessions et cache.
- Actuellement, la gestion des sessions semble être basée sur les tokens JWT stateless.

---

## Conclusion

La couche Infrastructure Layer est bien structurée avec :

- Une connexion MongoDB asynchrone performante et indexée.
- Une configuration centralisée et sécurisée via des variables d'environnement.
- Un système de sécurité robuste avec hashage des mots de passe et tokens JWT.
- Une base pour étendre la gestion du cache et des sessions si nécessaire.

Cette couche supporte efficacement les couches supérieures (API, Services, Modèles) en fournissant les fondations techniques nécessaires.

---

Si vous souhaitez, je peux vous aider à documenter ou améliorer d'autres parties du backend.
