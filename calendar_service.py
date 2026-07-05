# -*- coding: utf-8 -*-
"""Integracion con Google Calendar: listar y crear eventos, dar contexto
de agenda para la IA."""
import logging
import os
from datetime import datetime, timedelta

from config import TIMEZONE
from utils import escape_md

logger = logging.getLogger(__name__)


CALENDAR_TOKEN = None  # se lee de env var en runtime


def _get_calendar_service():
    """Construye el servicio Google Calendar con el token de cuenta 1."""
    try:
        from google.oauth2.credentials import Credentials
        import google.auth.transport.requests
        import googleapiclient.discovery

        client_id     = os.environ.get("GMAIL_CLIENT_ID", "").strip()
        client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
        refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN_1", "").strip().lstrip("=")
        if not refresh_token:
            logger.warning("Calendar: GMAIL_REFRESH_TOKEN_1 no configurado")
            return None
        if not client_id or not client_secret:
            logger.warning("Calendar: GMAIL_CLIENT_ID o GMAIL_CLIENT_SECRET no configurado")
            return None
        logger.info(f"Calendar: usando client_id={client_id[:20]}... token={refresh_token[:20]}...")
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=[
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/calendar',
            ],
        )
        req = google.auth.transport.requests.Request()
        creds.refresh(req)
        logger.info("Calendar: token refrescado OK")
        return googleapiclient.discovery.build('calendar', 'v3', credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Calendar service error FULL: {type(e).__name__}: {e}")
        return None


def _listar_eventos_sync(days_ahead: int = 7) -> list[dict]:
    """Lista los próximos eventos de todos los calendarios del usuario."""
    service = _get_calendar_service()
    if not service:
        return []
    try:
        now   = datetime.now(TIMEZONE)
        t_min = now.isoformat()
        t_max = (now + timedelta(days=days_ahead)).isoformat()

        # Obtener todos los calendarios del usuario
        cal_list = service.calendarList().list().execute()
        calendars = [c['id'] for c in cal_list.get('items', [])]
        if not calendars:
            calendars = ['primary']

        all_events = []
        seen_ids   = set()
        for cal_id in calendars:
            try:
                result = service.events().list(
                    calendarId=cal_id,
                    timeMin=t_min,
                    timeMax=t_max,
                    maxResults=20,
                    singleEvents=True,
                    orderBy='startTime',
                ).execute()
                for e in result.get('items', []):
                    if e['id'] in seen_ids:
                        continue
                    seen_ids.add(e['id'])
                    start = e['start'].get('dateTime', e['start'].get('date', ''))
                    all_events.append({
                        'id':     e['id'],
                        'titulo': e.get('summary', 'Sin título'),
                        'inicio': start,
                        'lugar':  e.get('location', ''),
                        'desc':   e.get('description', ''),
                    })
            except Exception:
                continue  # calendario sin acceso, ignorar

        # Ordenar por fecha de inicio
        all_events.sort(key=lambda x: x['inicio'])
        return all_events[:20]
    except Exception as e:
        logger.error(f"Calendar list error: {e}")
        return []


def _crear_evento_sync(titulo: str, fecha_iso: str, hora: str, duracion_min: int = 60) -> bool:
    """Crea un evento en Google Calendar. fecha_iso: YYYY-MM-DD, hora: HH:MM"""
    service = _get_calendar_service()
    if not service:
        return False
    try:
        tz_str = str(TIMEZONE)
        inicio = f"{fecha_iso}T{hora}:00"
        from datetime import datetime as _dt
        inicio_dt = _dt.fromisoformat(inicio)
        fin_dt    = inicio_dt + timedelta(minutes=duracion_min)
        fin       = fin_dt.strftime("%Y-%m-%dT%H:%M:00")

        event = {
            'summary':  titulo,
            'start':    {'dateTime': inicio, 'timeZone': tz_str},
            'end':      {'dateTime': fin,    'timeZone': tz_str},
        }
        service.events().insert(calendarId='primary', body=event).execute()
        return True
    except Exception as e:
        logger.error(f"Calendar create error: {e}")
        return False


def formatear_eventos(eventos: list[dict]) -> str:
    """Formatea la lista de eventos para Telegram MarkdownV2."""
    if not eventos:
        return "📅 _No tienes eventos próximos\\._"
    now = datetime.now(TIMEZONE)
    texto = "📅 *AGENDA*\n━━━━━━━━━━━━━━━\n\n"
    for e in eventos:
        inicio = e['inicio']
        try:
            if 'T' in inicio:
                dt = datetime.fromisoformat(inicio.replace('Z', '+00:00')).astimezone(TIMEZONE)
                dia   = dt.strftime('%a %d/%m')
                hora  = dt.strftime('%H:%M')
                label = escape_md(f"{dia} {hora}")
            else:
                dt    = datetime.fromisoformat(inicio)
                label = escape_md(dt.strftime('%a %d/%m'))
                hora  = "todo el día"
        except Exception:
            label = escape_md(inicio[:10])

        titulo = escape_md(e['titulo'])
        lugar  = f" 📍 {escape_md(e['lugar'])}" if e.get('lugar') else ""
        texto += f"🔹 *{titulo}*\n   _{label}{lugar}_\n\n"
    return texto.strip()


def get_calendar_context() -> str:
    """Contexto de calendario para el prompt de la IA (hoy + mañana)."""
    try:
        eventos = _listar_eventos_sync(days_ahead=2)
        if not eventos:
            return "Sin eventos en los próximos 2 días."
        lines = []
        for e in eventos:
            inicio = e['inicio']
            try:
                if 'T' in inicio:
                    dt   = datetime.fromisoformat(inicio.replace('Z', '+00:00')).astimezone(TIMEZONE)
                    when = dt.strftime('%a %d/%m %H:%M')
                else:
                    when = inicio
            except Exception:
                when = inicio
            lines.append(f"  {when}: {e['titulo']}")
        return "\n".join(lines)
    except Exception:
        return "No disponible."

