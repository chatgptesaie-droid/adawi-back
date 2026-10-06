# Showroom API - Backend E-commerce

Bienvenue sur le dépôt du backend **Showroom**, une solution e-commerce robuste et scalable construite avec **FastAPI** et **MongoDB**.

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

---

##  Fonctionnalités Clés

-  Authentification Sécurisée : Gestion des utilisateurs avec JWT (JSON Web Tokens) et cryptage des mots de passe.
-  Gestion de Catalogue : CRUD complet pour produits, catégories et gestion d'inventaire.
-  Système de Commandes : Workflow complet de commande, du panier au paiement et suivi de livraison.
-  Intégration de Paiement : Support natif pour **PayGate** et **MoneyFusion**.
-  Tableaux de Bord (BI) : Statistiques avancées pour les administrateurs et les vendeurs.
-  Support Client : Système de tickets et gestion des remboursements intégré.
-  CMS Intégré : Gestion dynamique de contenu (Pages, Blog, FAQ).
-  Temps Réel : Notifications via WebSockets pour une expérience utilisateur interactive.

---

## Stack Technique

- Framework : FastAPI (Python)
- Base de données : MongoDB (via Motor pour l'asynchrone)
- Validation : Pydantic v2
- Tâches planifiées : APScheduler
- Stockage Image : Cloudinary
- Emails : Resend API
- Serveur : Uvicorn

---

##  Structure du Projet

```text
├── app/
│   ├── api/          #  Routes et contrôleurs API
│   ├── core/         #  Configuration, sécurité et utilitaires
│   ├── db/           #  Connexion et indexation MongoDB
│   ├── models/       #  Schémas Pydantic et modèles de données
│   ├── services/     #  Logique métier et intégrations externes
│   └── main.py       #  Point d'entrée de l'application
├── tests/            #  Suite de tests unitaires et d'intégration
├── uploads/          #  Stockage local temporaire des fichiers
└── requirements.txt  #  Dépendances du projet
```

---

## Installation et Démarrage

### 1. Prérequis
- Python 3.9+
- MongoDB (local ou Atlas)

### 2. Installation
Clonez le dépôt et installez les dépendances :
```bash
git clone <repository-url>
cd ADAWI_backend
pip install -r requirements.txt
```

### 3. Configuration
Créez un fichier `.env` à la racine (utilisez `.env.example` comme modèle) :
```bash
cp .env.example .env
# Remplissez ensuite vos accès dans le fichier .env
```

### 4. Lancement
Démarrez le serveur de développement :
```bash
python start_server.py
```
L'API sera accessible sur `http://localhost:8000`.

---

## Documentation API

Une fois le serveur lancé, vous pouvez accéder à la documentation interactive :
- **Swagger UI** : `http://localhost:8000/docs`
- **ReDoc** : `http://localhost:8000/redoc`

---

## Sécurité
Si vous découvrez une faille de sécurité, merci de ne pas ouvrir de ticket public mais de contacter l'administrateur directement.

---

## Licence
Ce projet est sous licence privée. Toute reproduction ou distribution non autorisée est interdite.
