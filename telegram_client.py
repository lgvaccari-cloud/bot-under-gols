"""Envio de mensagens pro Telegram."""

import requests
import config


def enviar_mensagem(chat_id: str, texto: str):
    """Envia a mensagem e devolve o message_id (ou None se falhar)."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[telegram] Erro de rede ao enviar mensagem: {e}")
        return None
    if not resp.ok:
        print(f"[telegram] Falha ao enviar mensagem: {resp.status_code} {resp.text}")
        return None
    try:
        return resp.json()["result"]["message_id"]
    except Exception:
        return None


def editar_mensagem(chat_id: str, message_id: int, texto: str) -> bool:
    """Edita o texto de uma mensagem já enviada. True se deu certo."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": texto,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[telegram] Erro de rede ao editar mensagem: {e}")
        return False
    if not resp.ok:
        print(f"[telegram] Falha ao editar mensagem: {resp.status_code} {resp.text}")
        return False
    return True


def enviar_alerta(texto: str):
    return enviar_mensagem(config.CHAT_ID_ALERTAS, texto)


def enviar_relatorio_simulacao(texto: str):
    return enviar_mensagem(config.CHAT_ID_SIMULACAO, texto)
