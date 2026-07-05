# -*- coding: utf-8 -*-
"""
Capa de persistencia. Lee/escribe el estado del bot en Supabase (si esta
configurado) o en un archivo JSON local (fallback para desarrollo).
Incluye un cache de escritura (write-through) para evitar hacer una
peticion HTTP nueva por cada lectura/escritura dentro de una ventana corta.
"""
import copy
import json
import logging
import os
import time
from datetime import datetime

import requests

from config import (
    DATA_DIR, DATA_FILE, META_CAL_BASE, PENDING_ACTION_TTL_SECONDS,
    SUPABASE_ENABLED, SUPABASE_KEY, SUPABASE_TABLE_URL, TIMEZONE,
)

logger = logging.getLogger(__name__)


def _supabase_headers(extra=None):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    if extra:
        headers.update(extra)
    return headers


_data_cache = {"value": None, "ts": 0.0}


_CACHE_TTL_SECONDS = 3


def _load_raw_data():
    """Lee el JSON crudo desde Supabase (persistente) o desde el archivo local (fallback
    para desarrollo o si Supabase no está configurado)."""
    if SUPABASE_ENABLED:
        now = time.monotonic()
        if _data_cache["value"] is not None and (now - _data_cache["ts"]) < _CACHE_TTL_SECONDS:
            return copy.deepcopy(_data_cache["value"])
        try:
            resp = requests.get(
                SUPABASE_TABLE_URL,
                params={"id": "eq.1", "select": "data"},
                headers=_supabase_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            rows = resp.json()
            result = rows[0]["data"] if rows else {}
        except Exception as e:
            logger.error(f"No se pudo leer de Supabase ({e}), usando última copia en cache")
            result = _data_cache["value"] if _data_cache["value"] is not None else {}
        _data_cache["value"] = result
        _data_cache["ts"] = now
        return copy.deepcopy(result)
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"registro.json corrupto o ilegible ({e}), iniciando datos vacíos")
            return {}
    return {}


def load_data():
    data = _load_raw_data()
    data.setdefault("registros", [])
    data.setdefault("chat_id", None)
    data.setdefault("flow", None)
    data.setdefault("esperando", None)
    data.setdefault("gastos", [])
    data.setdefault("habitos", [])
    data.setdefault("habito_flow", None)
    data.setdefault("ai_history", [])
    data.setdefault("ai_last_message", None)
    data.setdefault("pending_action", None)
    data.setdefault("trades", [])
    data.setdefault("notas", [])
    data.setdefault("trade_pending", None)
    data.setdefault("trade_fotos", [])
    data.setdefault("recordatorios", [])
    data.setdefault("pasos", [])
    data.setdefault("calorias", [])
    data.setdefault("meta_calorias", META_CAL_BASE)
    data.setdefault("gmail_ingreso_pending", {})
    return data


def save_data(data):
    """Guarda en Supabase (persistente entre redeploys) si está configurado; si no,
    escritura atómica local (tmp+rename) para evitar registro.json corrupto."""
    if SUPABASE_ENABLED:
        try:
            resp = requests.patch(
                SUPABASE_TABLE_URL,
                params={"id": "eq.1"},
                headers=_supabase_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}),
                json={"data": data},
                timeout=10,
            )
            resp.raise_for_status()
            _data_cache["value"] = copy.deepcopy(data)
            _data_cache["ts"] = time.monotonic()
            return
        except Exception as e:
            logger.error(f"No se pudo guardar en Supabase ({e}), guardando copia local de respaldo")
            # continúa abajo: guarda copia local como respaldo para no perder el registro
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp_file = DATA_FILE + ".tmp"
    with open(tmp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)


def get_chat_id():
    # Primero intenta desde registro.json, luego variable de entorno CHAT_ID
    chat_id = load_data().get("chat_id")
    if not chat_id:
        env_id = os.environ.get("CHAT_ID", "").strip()
        if env_id:
            chat_id = int(env_id)
            set_chat_id(chat_id)  # guardarlo para siguientes llamadas
    return chat_id


def set_chat_id(chat_id):
    data = load_data(); data["chat_id"] = chat_id; save_data(data)


def get_flow():
    return load_data().get("flow")


def set_flow(tipo, paso, respuestas):
    data = load_data(); data["flow"] = {"tipo": tipo, "paso": paso, "respuestas": respuestas}; save_data(data)


def get_esperando():
    return load_data().get("esperando")


def set_esperando(tipo):
    data = load_data(); data["esperando"] = tipo; save_data(data)


def set_razonar_pending(original_msg: str, contexto: str = ""):
    data = load_data()
    data["razonar_pending"] = {"mensaje": original_msg, "contexto": contexto}
    data["esperando"] = "razonar"
    save_data(data)


def get_razonar_pending():
    return load_data().get("razonar_pending")


def clear_razonar_pending():
    data = load_data()
    data["razonar_pending"] = None
    data["esperando"] = None
    save_data(data)


def set_habito_flow(paso, respuestas):
    data = load_data(); data["habito_flow"] = {"paso": paso, "respuestas": respuestas}; save_data(data)


def set_trade_pending(tp):
    data = load_data(); data["trade_pending"] = tp; save_data(data)


def get_trade_pending():
    return load_data().get("trade_pending")


def clear_trade_pending():
    data = load_data(); data["trade_pending"] = None; save_data(data)


def get_ai_history():
    data = load_data()
    history = data.get("ai_history", [])
    last_time = data.get("ai_last_message")
    if last_time:
        try:
            last_dt = datetime.fromisoformat(last_time)
            if last_dt.tzinfo is None:
                last_dt = TIMEZONE.localize(last_dt)
            if (datetime.now(TIMEZONE) - last_dt).total_seconds() > 4 * 3600:
                return []
        except Exception:
            pass
    return history[-10:]


def save_ai_history(history, user_msg, assistant_msg):
    data = load_data()
    full = history + [
        {"role": "user",      "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    data["ai_history"] = full[-20:]
    data["ai_last_message"] = datetime.now(TIMEZONE).isoformat()
    save_data(data)


def set_pending_action(action):
    data = load_data()
    data["pending_action"] = {"action": action, "ts": datetime.now(TIMEZONE).isoformat()}
    save_data(data)


def get_pending_action():
    """Devuelve la acción pendiente, o None si ya expiró (evita que un botón
    de confirmación viejo dispare sobre una acción que ya no aplica)."""
    entry = load_data().get("pending_action")
    if not entry:
        return None
    if "action" not in entry or "ts" not in entry:
        return entry  # compatibilidad con formato antiguo
    try:
        ts = datetime.fromisoformat(entry["ts"])
        if ts.tzinfo is None:
            ts = TIMEZONE.localize(ts)
        if (datetime.now(TIMEZONE) - ts).total_seconds() > PENDING_ACTION_TTL_SECONDS:
            return None
    except Exception:
        pass
    return entry["action"]


def clear_pending_action():
    data = load_data(); data["pending_action"] = None; save_data(data)


def clear_all_flows():
    data = load_data()
    data["flow"] = None; data["esperando"] = None
    data["habito_flow"] = None; data["pending_action"] = None
    data["trade_pending"] = None
    save_data(data)


def get_sofia_mode() -> bool:
    return load_data().get("sofia_mode", False)


def set_sofia_mode(active: bool):
    data = load_data(); data["sofia_mode"] = active; save_data(data)


def get_sofia_history() -> list:
    """Retorna los últimos 40 mensajes para la conversación activa. Sin expiración — memoria permanente."""
    return load_data().get("sofia_history", [])[-40:]


def get_sofia_context_summary() -> str:
    """Resumen de toda la historia acumulada con Sofía para el system prompt."""
    data = load_data()
    history = data.get("sofia_history", [])
    if not history:
        return "Sin conversaciones previas con Sofía."
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    total = len(user_msgs)
    if total == 0:
        return "Sin conversaciones previas."
    # Mostrar muestra representativa: primeros 5 + últimos 15
    if total <= 20:
        sample = user_msgs
    else:
        sample = user_msgs[:5] + ["..."] + user_msgs[-15:]
    lines = [f"Total de intercambios guardados: {total} mensajes del usuario."]
    lines.append("Muestra de temas platicados (para contexto histórico):")
    for msg in sample:
        if msg == "...":
            lines.append("  [...sesiones anteriores...]")
        else:
            lines.append(f"  - {msg[:120]}")
    return "\n".join(lines)


def save_sofia_history(history: list, user_msg: str, assistant_msg: str):
    data = load_data()
    # Acumulamos sobre el historial total guardado en data, no solo la sesión activa
    full = data.get("sofia_history", []) + [
        {"role": "user",      "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    data["sofia_history"] = full[-300:]  # guardar hasta 300 mensajes (~150 intercambios)
    data["sofia_last_message"] = datetime.now(TIMEZONE).isoformat()
    save_data(data)

