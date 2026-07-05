# -*- coding: utf-8 -*-
"""Integracion con Gmail: leer correos, detectar transacciones financieras
automaticamente (usando la IA) y clasificarlas."""
import logging
import os

from ai_service import groq_client

logger = logging.getLogger(__name__)


def _get_gmail_service(refresh_token: str):
    """Construye el servicio Gmail con refresh_token. Retorna None si falta config."""
    try:
        from google.oauth2.credentials import Credentials
        import google.auth.transport.requests
        import googleapiclient.discovery

        refresh_token = refresh_token.strip().lstrip("=")
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.environ.get("GMAIL_CLIENT_ID", ""),
            client_secret=os.environ.get("GMAIL_CLIENT_SECRET", ""),
            scopes=['https://www.googleapis.com/auth/gmail.readonly'],
        )
        req = google.auth.transport.requests.Request()
        creds.refresh(req)
        return googleapiclient.discovery.build('gmail', 'v1', credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.warning(f"Gmail service error: {e}")
        return None


def _extract_email_body(msg: dict) -> str:
    """Extrae texto plano del payload del mensaje Gmail."""
    import base64 as b64mod
    import re as remod

    def decode_part(data: str) -> str:
        try:
            return b64mod.urlsafe_b64decode(data + '==').decode('utf-8', errors='replace')
        except Exception:
            return ""

    def strip_html(html: str) -> str:
        text = remod.sub(r'<[^>]+>', ' ', html)
        text = remod.sub(r'[ \t]+', ' ', text)
        text = remod.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    payload = msg.get('payload', {})
    parts   = payload.get('parts', [])

    # Mensajes sin partes (body directo)
    if not parts:
        data = payload.get('body', {}).get('data', '')
        text = decode_part(data)
        if payload.get('mimeType', '') == 'text/html':
            text = strip_html(text)
        return text[:3000]

    # Buscar text/plain primero, luego text/html
    plain_text = ""
    html_text  = ""

    def walk_parts(parts_list):
        nonlocal plain_text, html_text
        for part in parts_list:
            mime = part.get('mimeType', '')
            data = part.get('body', {}).get('data', '')
            sub  = part.get('parts', [])
            if sub:
                walk_parts(sub)
            elif mime == 'text/plain' and data:
                plain_text += decode_part(data)
            elif mime == 'text/html' and data:
                html_text += strip_html(decode_part(data))

    walk_parts(parts)
    result = plain_text or html_text
    return result[:3000]


def _parse_email_keywords(subject: str, from_addr: str, body: str) -> dict | None:
    """
    Clasificación por palabras clave — fallback cuando Groq no está disponible.
    Detecta emails financieros en español/inglés y extrae monto.
    """
    import re as _re
    texto = f"{subject} {body}".lower()

    # Palabras que indican transacción financiera
    palabras_financieras = [
        "depósito", "deposito", "abono", "transferencia", "pago recibido",
        "cargo", "compra", "retiro", "movimiento", "transacción", "transaccion",
        "ingreso", "cobro", "débito", "debito", "crédito", "credito",
        "received", "payment", "transaction", "purchase", "withdrawal", "deposit",
        "spei", "oxxo pay", "clip", "mercado pago", "paypal",
    ]
    if not any(p in texto for p in palabras_financieras):
        return None

    # Detectar tipo
    tipo = "gasto"
    if any(p in texto for p in ["depósito", "deposito", "abono", "recibiste", "ingreso",
                                  "received", "deposit", "pago recibido", "te enviaron"]):
        tipo = "ingreso"
    elif any(p in texto for p in ["transferencia entre", "movimiento entre tus", "tu mismo"]):
        tipo = "transferencia"

    # Extraer monto — busca patrones como $1,234.56 o 1234.56 o 1,234
    monto = 0.0
    patrones = [
        r'\$\s*([\d,]+\.?\d*)',
        r'([\d,]+\.\d{2})\s*(?:pesos|mxn|usd)',
        r'monto[:\s]+([\d,]+\.?\d*)',
        r'importe[:\s]+([\d,]+\.?\d*)',
        r'cantidad[:\s]+([\d,]+\.?\d*)',
        r'amount[:\s]+([\d,]+\.?\d*)',
    ]
    for pat in patrones:
        m = _re.search(pat, texto, _re.IGNORECASE)
        if m:
            try:
                monto = float(m.group(1).replace(",", ""))
                if monto > 0:
                    break
            except ValueError:
                continue

    comercio = from_addr.split('<')[0].strip()[:40] or "desconocido"
    return {"tipo": tipo, "monto": monto, "comercio": comercio, "descripcion": subject[:50]}


def _parse_email_financial_sync(subject: str, from_addr: str, body: str) -> dict | None:
    """
    Usa Groq para decidir si el email es financiero y extraer datos.
    Si Groq falla, usa clasificación por palabras clave como fallback.
    """
    prompt = (
        "Analiza este email bancario/financiero.\n\n"
        f"De: {from_addr[:100]}\n"
        f"Asunto: {subject[:150]}\n"
        f"Cuerpo:\n{body[:1500]}\n\n"
        "Si ES una transacción financiera responde EXACTAMENTE así (sin nada más):\n"
        "FINANCIERO|TIPO:[gasto/ingreso/transferencia]|MONTO:[número]|"
        "COMERCIO:[nombre del comercio o destinatario, máx 40 chars, o 'desconocido']|"
        "DESC:[descripción corta máx 50 chars]\n\n"
        "Si NO es financiero responde solo: NO_FINANCIERO\n\n"
        "Tipos: gasto=dinero que sale a un comercio/persona, "
        "ingreso=dinero que entra a tu cuenta, "
        "transferencia=movimiento entre tus propias cuentas."
    )
    groq_ok = bool(os.environ.get("GROQ_API_KEY", "").strip())
    if groq_ok:
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0,
            )
            text = resp.choices[0].message.content.strip()
            if not text.startswith("FINANCIERO"):
                return None
            parts = text.split("|")
            result = {}
            for p in parts[1:]:
                if p.startswith("TIPO:"):
                    result["tipo"] = p[5:].strip().lower()
                elif p.startswith("MONTO:"):
                    try:
                        result["monto"] = float(p[6:].strip().replace(",", ""))
                    except ValueError:
                        result["monto"] = 0.0
                elif p.startswith("COMERCIO:"):
                    result["comercio"] = p[9:].strip()
                elif p.startswith("DESC:"):
                    result["descripcion"] = p[5:].strip()
            if "monto" in result:
                return result
            # Groq respondió FINANCIERO pero sin monto — usar keywords
        except Exception as e:
            logger.warning(f"Gmail Groq parse error: {e} — usando fallback keywords")

    # Fallback: clasificación por palabras clave (sin IA)
    return _parse_email_keywords(subject, from_addr, body)


def _fetch_gmail_transactions_sync(refresh_token: str, last_history_id: str | None, window_hours: int = 1) -> list[dict]:
    """Busca emails financieros nuevos. Retorna lista de transacciones detectadas."""
    service = _get_gmail_service(refresh_token)
    if not service:
        return []

    import time as time_mod
    since_unix = int(time_mod.time()) - window_hours * 3600
    logger.info(f"Gmail search: últimas {window_hours}h (desde unix {since_unix})")
    # Usar timestamp Unix directamente — más preciso que date string
    query = f"after:{since_unix}"
    try:
        result = service.users().messages().list(userId='me', q=query, maxResults=20).execute()
        messages = result.get('messages', [])
        logger.info(f"Gmail: {len(messages)} emails encontrados")
    except Exception as e:
        logger.error(f"Gmail list error: {e}")
        return []

    transactions = []
    for msg_ref in messages:
        msg_id = msg_ref['id']
        try:
            full = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            headers = {h['name']: h['value'] for h in full.get('payload', {}).get('headers', [])}
            subject   = headers.get('Subject', '')
            from_addr = headers.get('From', '')
            body      = _extract_email_body(full)

            parsed = _parse_email_financial_sync(subject, from_addr, body)
            if parsed:
                transactions.append({
                    "email_id": msg_id,
                    "subject":  subject[:100],
                    "from":     from_addr[:80],
                    **parsed,
                })
        except Exception as e:
            logger.warning(f"Gmail fetch msg {msg_id} error: {e}")
            continue

    return transactions

