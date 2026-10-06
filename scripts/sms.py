"""
Service SMS via NGH SMS API
============================
Host   : extranet.nghcorp.net
Route  : POST /api/send-sms
Données: JSON
Réponse: { "status": 200, "status_desc": "Success", "messageid": "...", "credits": ... }

TODO : Remplis les 3 champs ci-dessous avec tes identifiants NGH.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.sms_service import send_sms

def send_sms_bulk(contacts: list, message: str) -> list:
    """
    Envoie le même SMS à une liste de numéros.

    Args:
        contacts : Liste de numéros, ex: [22890000000, 22870000000]
        message  : Texte du message

    Returns:
        Liste de résultats pour chaque numéro
    """
    results = []
    for idx, contact in enumerate(contacts):
        result = send_sms(contact, message, reference=idx + 1)
        result["contact"] = contact
        status = "✓" if result["success"] else "✗"
        print(f"  {status} {contact} : {result['status_desc']}")
        results.append(result)
    return results


# ─────────────────────────────────────────────────────────────
# Templates de messages Adawi
# ─────────────────────────────────────────────────────────────

def msg_commande_confirmee(nom: str, ref: str) -> str:
    return f"Bonjour {nom}, votre commande {ref} est confirmée. Merci pour votre achat ! - ADAWI"

def msg_commande_expediee(nom: str, ref: str) -> str:
    return f"Bonjour {nom}, votre commande {ref} est en cours de livraison. Vous serez contacté. - ADAWI"

def msg_commande_livree(nom: str, ref: str) -> str:
    return f"Bonjour {nom}, votre commande {ref} a bien été livrée. Bonne utilisation ! - ADAWI"

def msg_commande_annulee(nom: str, ref: str) -> str:
    return f"Bonjour {nom}, votre commande {ref} a été annulée. Contactez-nous pour plus d'infos. - ADAWI"

def msg_remboursement(nom: str, montant: str) -> str:
    return f"Bonjour {nom}, votre remboursement de {montant} FCFA a été initié (2-3 jours ouvrables). - ADAWI"

def msg_nouveau_compte(nom: str) -> str:
    return f"Bienvenue {nom} ! Votre compte ADAWI a été créé avec succès. Bonne expérience de shopping !"


# ─────────────────────────────────────────────────────────────
# Test manuel — python scripts/sms.py --to 22890000000 --message "Test SMS"
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envoyer un SMS de test via NGH.")
    parser.add_argument("--to", required=True, help="Numéro du destinataire")
    parser.add_argument("--message", required=True, help="Texte du SMS")
    parser.add_argument("--reference", type=int, default=0)
    args = parser.parse_args()
    result = send_sms(args.to, args.message, reference=args.reference)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["success"] else 1)
