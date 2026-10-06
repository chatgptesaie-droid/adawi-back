"""NGH SMS delivery helpers for customer-facing events."""

import asyncio
import http.client
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)
NGH_HOST = "extranet.nghcorp.net"
NGH_ENDPOINT = "/api/send-sms"
TOGO_TIMEZONE = ZoneInfo("Africa/Lome")
STATUS_LABELS = {
    "en_cours": "en cours",
    "en_preparation": "en préparation",
    "expediee": "expédiée",
    "livree": "livrée",
    "annulee": "annulée",
    "boutique": "disponible en boutique",
    "resolu": "résolu",
    "ferme": "fermé",
    "pending": "en attente",
    "approved": "approuvé",
    "rejected": "refusé",
    "processed": "effectué",
}


def normalize_togo_phone(phone: str | int) -> str:
    digits = re.sub(r"[^0-9]", "", str(phone))
    if digits.startswith("00228"):
        return digits[2:]
    if not digits.startswith("228"):
        return f"228{digits}"
    return digits


def send_sms(to: int | str, message: str, reference: int = 0) -> dict:
    """Send one SMS through NGH. Credentials are read from environment variables."""
    api_key = os.getenv("NGH_API_KEY", "")
    api_secret = os.getenv("NGH_API_SECRET", "")
    sender_id = os.getenv("NGH_SENDER_ID", "")
    if not api_key or not api_secret or not sender_id:
        return {
            "success": False,
            "status": -1,
            "status_desc": "Configuration NGH manquante (NGH_API_KEY, NGH_API_SECRET, NGH_SENDER_ID).",
            "message_id": "",
            "credits": 0,
            "raw": None,
        }

    digits = normalize_togo_phone(to)
    if not digits:
        return {
            "success": False,
            "status": -1,
            "status_desc": "Numéro de téléphone invalide.",
            "message_id": "",
            "credits": 0,
            "raw": None,
        }

    payload = json.dumps({
        "from": sender_id,
        "to": int(digits),
        "text": message,
        "reference": reference,
        "api_key": api_key,
        "api_secret": api_secret,
    })
    connection = None
    try:
        connection = http.client.HTTPSConnection(NGH_HOST, timeout=10)
        connection.request(
            "POST",
            NGH_ENDPOINT,
            payload,
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response_body = response.read().decode("utf-8")
        result = json.loads(response_body)
        success = response.status < 400 and result.get("status") == 200
        return {
            "success": success,
            "status": result.get("status", response.status),
            "status_desc": result.get("status_desc", response.reason),
            "message_id": result.get("messageid", ""),
            "credits": result.get("credits", 0),
            "raw": result,
        }
    except Exception as error:
        return {
            "success": False,
            "status": -1,
            "status_desc": f"Erreur NGH : {error}",
            "message_id": "",
            "credits": 0,
            "raw": None,
        }
    finally:
        if connection:
            connection.close()


def customer_phone(user: dict | None = None, order: dict | None = None) -> str | None:
    """Find the customer's phone across current profile and order data shapes."""
    user = user or {}
    order = order or {}
    address = order.get("address") or user.get("address") or {}
    phone = (
        order.get("customer_phone")
        or order.get("phone")
        or address.get("phone")
        or user.get("phone")
        or user.get("phone_number")
        or user.get("telephone")
    )
    return str(phone).strip() if phone else None


def customer_name(user: dict | None = None, fallback: str = "Client") -> str:
    user = user or {}
    full_name = user.get("full_name") or " ".join(
        part for part in (user.get("prenom"), user.get("nom")) if part
    )
    return str(full_name or fallback).strip()


def status_label(status: object) -> str:
    value = getattr(status, "value", status)
    text = str(value)
    return STATUS_LABELS.get(text, text.replace("_", " "))


def short_reference(reference: str | int) -> str:
    return f"#{str(reference)[-6:]}"


def order_status_message(status: object, order_id: str | int) -> str:
    value = str(getattr(status, "value", status))
    reference = short_reference(order_id)
    if value == "expediee":
        return f"Votre commande {reference} est en cours de route."
    if value == "livree":
        return f"Votre commande {reference} a été livrée."
    return f"Le statut de votre commande {reference} est maintenant {status_label(status)}."


def mask_phone(phone: str | int) -> str:
    digits = re.sub(r"[^0-9]", "", str(phone))
    return f"***{digits[-4:]}" if digits else "***"


async def send_customer_sms(
    phone: str | int | None,
    name: str,
    message: str,
    reference: int = 0,
    occurred_at: datetime | None = None,
    event: str = "customer_notification",
) -> dict:
    """Send a timestamped, named customer SMS without blocking business actions."""
    if not phone:
        logger.warning("SMS ignoré: téléphone absent (event=%s)", event)
        return {"success": False, "status": -1, "status_desc": "Téléphone client absent."}

    timestamp = occurred_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    local_time = timestamp.astimezone(TOGO_TIMEZONE).strftime("%d/%m/%Y à %H:%M")
    text = f"Bonjour {name or 'Client'}, le {local_time}. {message} - ADAWI"
    masked_phone = mask_phone(phone)
    logger.info("SMS NGH en cours (event=%s, phone=%s, reference=%s)", event, masked_phone, reference)
    result = await asyncio.to_thread(send_sms, phone, text, reference)
    if result["success"]:
        logger.info(
            "SMS accepté par NGH (livraison non confirmée; event=%s, phone=%s, status=%s, status_desc=%s, message_id=%s, credits=%s)",
            event,
            masked_phone,
            result.get("status"),
            result.get("status_desc"),
            result.get("message_id"),
            result.get("credits"),
        )
    else:
        logger.error(
            "Échec SMS NGH (event=%s, phone=%s, status=%s): %s",
            event,
            masked_phone,
            result.get("status"),
            result.get("status_desc"),
        )
    return result