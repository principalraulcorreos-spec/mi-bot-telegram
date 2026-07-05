# -*- coding: utf-8 -*-
"""Noticias de forex/economicas para las divisas configuradas."""
import asyncio
import logging
from datetime import datetime, timedelta

import pytz

from config import TIMEZONE
from utils import _split_text

logger = logging.getLogger(__name__)


_FOREX_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"}


def _fetch_forex_news_sync(target_date=None, days=1):
    """Descarga eventos de alto impacto vía FXStreet Calendar API (volatility=3)."""
    import requests as req_lib

    mx_tz = TIMEZONE
    if target_date is None:
        target_date = datetime.now(mx_tz).date()

    end_date = target_date + timedelta(days=days)

    url = "https://calendar.fxstreet.com/eventdate/"
    params = {
        "f":          "json",
        "v":          "2",
        "dateFrom":   target_date.strftime("%Y-%m-%d"),
        "dateTo":     end_date.strftime("%Y-%m-%d"),
        "timezone":   "America/Mexico_City",
        "cultures":   "en-US",
        "volatility": "3",  # 3 = High impact only
    }
    headers = {
        "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":      "application/json",
        "Referer":     "https://www.fxstreet.com/economic-calendar",
    }

    fetch_ok = False
    all_events = []
    try:
        resp = req_lib.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        raw_events = resp.json()
        fetch_ok = True
        logger.info(f"FXStreet: {len(raw_events) if isinstance(raw_events, list) else 'N/A'} eventos")
        if raw_events:
            logger.info(f"FXStreet primer evento completo: {raw_events[0]}")

        for ev in raw_events:
            event_obj = ev.get("Event", {})
            # CurrencyId contiene el código ISO (ej: "USD")
            currency = (event_obj.get("CurrencyId") or "").upper()
            if currency not in _FOREX_CURRENCIES:
                continue

            date_str = ev.get("DateUtc", "")
            try:
                dt_utc = datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.utc)
            except Exception:
                continue
            dt_mx = dt_utc.astimezone(mx_tz)

            if not (target_date <= dt_mx.date() < end_date):
                continue

            title    = event_obj.get("Name", "").strip()
            hora_mx  = dt_mx.strftime("%a %d/%m %H:%M") if days > 1 else dt_mx.strftime("%H:%M")
            sort_key = dt_mx.toordinal() * 1440 + dt_mx.hour * 60 + dt_mx.minute
            forecast = ev.get("Consensus")
            previous = ev.get("Previous")

            all_events.append({
                "title":    title,
                "country":  currency,
                "hora_mx":  hora_mx,
                "forecast": str(forecast) if forecast is not None else "",
                "previous": str(previous) if previous is not None else "",
                "sort_key": sort_key,
            })

    except Exception as e:
        logger.warning(f"FXStreet calendar fetch error: {e}")

    all_events.sort(key=lambda x: x['sort_key'])
    return all_events, fetch_ok


def _format_forex_news(events, fecha_label="hoy", fetch_ok=True):
    if not fetch_ok:
        return f"⚠️ No pude conectar con el calendario {fecha_label}. Revisa en TradingView o FTMO."
    if not events:
        return f"📰 Sin noticias de alto impacto {fecha_label}."
    lines = [f"🔴 NOTICIAS ALTO IMPACTO — {fecha_label.upper()}\n{'─'*30}\n"]
    for e in events:
        pais   = e['country']
        titulo = e['title']
        hora   = e['hora_mx']
        extras = []
        if e.get('forecast'):
            extras.append(f"est: {e['forecast']}")
        if e.get('previous'):
            extras.append(f"prev: {e['previous']}")
        extra_txt = f"  ({', '.join(extras)})" if extras else ""
        lines.append(f"🕐 {hora} | {pais} — {titulo}{extra_txt}")
    lines.append("\nHora: Ciudad de México")
    return "\n".join(lines)


async def _send_noticias(bot_or_update, chat_id, target_date, label, days=1, edit_msg=None):
    """Helper compartido: fetch y envío de noticias."""
    events, fetch_ok = await asyncio.wait_for(
        asyncio.to_thread(_fetch_forex_news_sync, target_date, days),
        timeout=25
    )
    texto = _format_forex_news(events, label, fetch_ok)
    chunks = _split_text(texto)
    if edit_msg:
        await edit_msg.edit_text(chunks[0])
        for chunk in chunks[1:]:
            await edit_msg.reply_text(chunk)
    else:
        for chunk in chunks:
            await bot_or_update.send_message(chat_id=chat_id, text=chunk)

