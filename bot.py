# -*- coding: utf-8 -*-
import base64
import json
import logging
import os
import re
import random
import asyncio
from datetime import datetime, time as dt_time, timedelta
from calendar import monthcalendar, FRIDAY

import pytz
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN      = os.environ["BOT_TOKEN"]
TIMEZONE   = pytz.timezone('America/Mexico_City')
DATA_DIR   = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DATA_FILE  = os.path.join(DATA_DIR, "registro.json")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

# ------------------------------------
# UTILIDADES (primero — todo lo usa)
# ------------------------------------

def escape_md(text):
    chars = r'_*[]()~`>#+-=|{}.!'
    for c in chars:
        text = str(text).replace(c, f'\\{c}')
    return text

# ------------------------------------
# PRESUPUESTO MENSUAL
# ------------------------------------

PRESUPUESTO = {
    "comida":      1200,
    "transporte":   600,
    "capricho":     500,
    "ropa":         300,
    "salud":        300,
    "otros":        400,
}

CATEGORIAS_ALIAS = {
    "café": "comida", "cafe": "comida", "food": "comida",
    "super": "comida", "súper": "comida", "mercado": "comida",
    "uber": "transporte", "taxi": "transporte",
    "camion": "transporte", "camión": "transporte", "bus": "transporte",
    "antojo": "capricho", "gusto": "capricho", "impulsivo": "capricho",
    "medicina": "salud", "doctor": "salud", "farmacia": "salud",
}

GASTO_RE = re.compile(
    r'^(?:gasto|gaste|gasté|gastaste)\s+\$?(\d+(?:\.\d+)?)\s+(\w+)',
    re.IGNORECASE
)

# ------------------------------------
# HÁBITOS
# ------------------------------------

HABITOS = [
    ("gym",          "💪 ¿Hiciste gym hoy?"),
    ("comida_casa",  "🍽 ¿Comiste en casa según lo planeado?"),
    ("trading_plan", "📈 ¿Respetaste tu estrategia de trading hoy?"),
    ("templanza",    "🧠 ¿Lograste no masturbarte hoy?"),
]

# ------------------------------------
# TRADES — emociones
# ------------------------------------

EMOCIONES_TRADE = [
    ("plan",       "✅ Según el plan"),
    ("miedo",      "😰 Salí por miedo"),
    ("impaciente", "😤 Cerré antes"),
    ("sl",         "🔴 Stop loss"),
]

# ------------------------------------
# SALUD & FITNESS
# ------------------------------------

RUTINA_LMV = [
    ("Calentamiento",    "10-15 min cardio suave (caminata/bici)"),
    ("Pecho & Triceps",  "Press plano 4x10 | Fondos 3x12 | Extensiones 3x15"),
    ("Espalda & Biceps", "Jalones 4x10 | Remo 3x12 | Curl 3x15"),
    ("Pierna",           "Sentadilla 4x10 | Prensa 3x12 | Extensiones 3x15"),
    ("Core",             "Plancha 3x45s | Abdominales 3x20"),
    ("Enfriamiento",     "10 min stretching completo"),
]

# Ultimo sabado de corte: 2026-04-25 (cada 2 semanas = sabados alternos)
CORTE_CABELLO_BASE = "2026-04-25"

META_PASOS_DIARIO = 8000
META_CAL_BASE     = 2000  # se actualiza automático con el peso

def _calcular_meta_calorias(peso_kg: float) -> int:
    """Mifflin-St Jeor para hombre activo (actividad moderada)."""
    # Asume: hombre, 25 años, 175 cm, actividad moderada (x1.55)
    tmb = 10 * peso_kg + 6.25 * 175 - 5 * 25 + 5
    return round(tmb * 1.55)

# ------------------------------------
# FRASES MOTIVACIONALES
# ------------------------------------

FRASES_RAW = [
    "El Raúl del futuro te lo agradece. Sigue así.",
    "Cada registro es una promesa cumplida contigo mismo.",
    "La disciplina hoy es libertad mañana. No pares.",
    "Lo que se mide, mejora. Ya diste el paso más difícil.",
    "El mercado no perdona la inconsistencia. Tú ya la estás atacando.",
    "Jehová ve el corazón. El tuyo va en la dirección correcta.",
    "Los pequeños compromisos diarios construyen vidas extraordinarias.",
    "No es motivación, es identidad. Tú eres el tipo que cumple.",
    "Cada peso registrado es un peso bajo control.",
    "La semana se construye hábito por hábito. Tú ya lo sabes.",
]

def frase_aleatoria():
    return escape_md(random.choice(FRASES_RAW))

# ------------------------------------
# PREGUNTAS SEMANAL
# ------------------------------------

PREGUNTAS_SEMANAL = [
    (
        "1️⃣ EL PULSO DE LA SEMANA",
        "• Control vs Reacción: ¿80% control o te arrastró la semana?\n"
        "• Emoción dominante: ¿Calma o ansiedad?\n"
        "• ¿Dónde estuviste a punto de traicionarte?"
    ),
    (
        "2️⃣ DINERO Y EL RAÚL DEL FUTURO",
        "• ¿Qué % de tus gastos fueron fugas?\n"
        "• ¿Le robaste al Raúl del futuro? ¿Cuál fue el disparador?\n"
        "• ¿En qué momento dijiste NO a un gasto impulsivo?"
    ),
    (
        "3️⃣ SISTEMAS Y TRADING",
        "• Del 1 al 10, ¿cuánto respetaste tu estrategia?\n"
        "• ¿Cerraste trades por miedo o incomodidad?\n"
        "• ¿Esperaste tu configuración o forzaste entradas?"
    ),
    (
        "4️⃣ TEMPLANZA E IMPULSOS",
        "• ¿Cediste a impulsos carnales o transmitiste esa energía?\n"
        "• ¿Comiste en casa según lo planeado?"
    ),
    (
        "5️⃣ HUMILDAD Y CARÁCTER",
        "• ¿Reconociste que aún estás aprendiendo?\n"
        "• ¿Aceptaste corrección o te defendiste por orgullo silencioso?"
    ),
    (
        "6️⃣ RELACIONES Y PAZ",
        "• ¿Fuiste un apoyo real para tu familia y amigos?\n"
        "• ¿Hablaste desde la verdad o desde el cálculo?"
    ),
    (
        "7️⃣ CIERRE",
        "Calificación de la semana (1-10): ___\n"
        "¿Qué UNA cosa harás diferente el lunes?"
    ),
]

# ------------------------------------
# PREGUNTAS MENSUAL
# ------------------------------------

PREGUNTAS_MENSUAL = [
    (
        "1️⃣ ESTE MES, ¿CÓMO VIVISTE?",
        "• ¿Respondiste a la vida o la dirigiste?\n"
        "• ¿Qué emoción dominó más tus días?\n"
        "• ¿En qué momentos te traicionaste?"
    ),
    (
        "2️⃣ DINERO",
        "• ¿Tu dinero te dio paz o estrés este mes?\n"
        "• ¿Gastaste con intención o por impulso?\n"
        "• ¿Qué decisión financiera repetirías? ¿Cuál no?"
    ),
    (
        "3️⃣ DISCIPLINA Y HÁBITOS",
        "• ¿Qué hábito pequeño sí cumpliste?\n"
        "• ¿Dónde te mentiste diciendo \"luego\"?\n"
        "• ¿Qué hábito sostenido 30 días más te cambiaría el año?"
    ),
    (
        "4️⃣ RELACIONES",
        "• ¿A quién cuidaste de verdad?\n"
        "• ¿Fuiste refugio emocional o carga?"
    ),
    (
        "5️⃣ FE / VIDA INTERIOR",
        "• ¿Este mes confiaste incluso sin entender?\n"
        "• ¿Qué agradeces sinceramente?"
    ),
    (
        "6️⃣ BALANCE MENSUAL",
        "Califica del 1 al 10: Orden / Paz / Avance / Honestidad / Humildad\n\n"
        "\"Este mes aprendí que ___.\"\n"
        "\"El próximo mes me enfocaré en ___.\""
    ),
]

# ------------------------------------
# MENSAJES FIJOS
# ------------------------------------

CAPITAL = (
    "💰 *RAÚL — TU DINERO DEL MES ESPERA ÓRDENES*\n"
    "━━━━━━━━━━━━━━━\n"
    "💰 *DIVISIÓN DE CAPITAL*\n"
    "━━━━━━━━━━━━━━━\n\n"
    "Renta recibida: *$8,000 pesos*\n"
    "\\(\\-400 mantenimiento \\= $7,600 disponibles\\)\n\n"
    "¿Cuánto va a cada área?\n"
    "• 📈 Trading / Inversión: $\\_\\_\\_\n"
    "• 🍽 Gastos del mes: $\\_\\_\\_\n"
    "• 🏦 Ahorro \\(CETES\\): $\\_\\_\\_\n"
    "• 🔧 Mantenimiento: $400 \\(fijo\\)\n\n"
    "*Total debe ser $8,000*\n\n"
    "━━━━━━━━━━━━━━━\n"
    "📝 *Define tu capital ahora mismo\\.* 👇"
)

PEDIR_INFORME = (
    "📲 *RAÚL — PIDE LOS INFORMES HOY*\n"
    "━━━━━━━━━━━━━━━\n\n"
    "📱 Manda este WhatsApp a los hermanos *ahora*:\n\n"
    "_\"Hermanos, ya es fin de mes\\. Por favor envíenme su informe cuando puedan\\. Gracias\\.\"_\n\n"
    "━━━━━━━━━━━━━━━\n"
    "⚠️ *No lo dejes para mañana\\.*"
)

ENVIAR_INFORME = (
    "🚨 *RAÚL — HOY ES EL LÍMITE\\. ENVÍA EL INFORME*\n"
    "━━━━━━━━━━━━━━━\n\n"
    "⚠️ Hoy es el día 4\\. *Límite hoy\\.* ⚠️\n\n"
    "Recopila los informes recibidos y envíalos\n"
    "a la persona correspondiente de la congregación\\.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "📤 *Hazlo antes de las 12PM\\.* ⏰"
)

# ------------------------------------
# TECLADOS
# ------------------------------------

def menu_keyboard():
    """Menú principal — 6 módulos + Sofía."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Finanzas",   callback_data='mod_finanzas'),
            InlineKeyboardButton("📈 Trading",    callback_data='mod_trading'),
        ],
        [
            InlineKeyboardButton("💪 Salud",      callback_data='mod_salud'),
            InlineKeyboardButton("📅 Agenda",     callback_data='mod_agenda'),
        ],
        [
            InlineKeyboardButton("📊 Reportes",   callback_data='mod_reportes'),
            InlineKeyboardButton("📝 Notas",      callback_data='notas'),
        ],
        [
            InlineKeyboardButton("🧠 Hablar con Sofía", callback_data='sofia_modo'),
        ],
    ])

def _volver():
    return [InlineKeyboardButton("⬅️ Menú principal", callback_data='menu')]

def finanzas_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Ingresos del mes",  callback_data='fin_ingresos'),
            InlineKeyboardButton("💸 Gastos del mes",    callback_data='fin_gastos'),
        ],
        [
            InlineKeyboardButton("⚖️ Balance actual",    callback_data='fin_balance'),
            InlineKeyboardButton("🔄 Movimientos",       callback_data='fin_movimientos'),
        ],
        [_volver()[0]],
    ])

def trading_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 Fotos de trades",   callback_data='fotos_trades'),
        ],
        [_volver()[0]],
    ])

def salud_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏥 Dashboard hoy",     callback_data='sal_dashboard'),
            InlineKeyboardButton("⚖️ Peso",              callback_data='sal_peso'),
        ],
        [
            InlineKeyboardButton("👟 Pasos/Calorías",    callback_data='sal_pasos'),
            InlineKeyboardButton("🏋️ Rutina L/M/V",     callback_data='sal_rutina'),
        ],
        [_volver()[0]],
    ])

def agenda_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Ver agenda 7 días", callback_data='age_ver'),
            InlineKeyboardButton("🗓️ Agenda de hoy",     callback_data='age_hoy'),
        ],
        [_volver()[0]],
    ])

def reportes_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 ¿Cómo voy?",        callback_data='como_voy'),
            InlineKeyboardButton("📊 Reporte mensual",   callback_data='rep_mensual'),
        ],
        [
            InlineKeyboardButton("💪 Hábitos del mes",   callback_data='rep_habitos'),
        ],
        [_volver()[0]],
    ])

def historial_keyboard():
    """Legacy — mantenido por si se llama desde algún comando."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Semanales", callback_data='hist_semanal'),
            InlineKeyboardButton("🧠 Mensuales", callback_data='hist_mensual'),
        ],
        [
            InlineKeyboardButton("💰 Capital",   callback_data='hist_capital'),
            InlineKeyboardButton("📋 Todo",      callback_data='hist_todo'),
        ],
        [_volver()[0]],
    ])

def habito_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sí", callback_data='hab_si'),
            InlineKeyboardButton("❌ No", callback_data='hab_no'),
        ]
    ])

def confirm_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Registrar", callback_data='accion_si'),
            InlineKeyboardButton("❌ No",        callback_data='accion_no'),
        ]
    ])

def trade_confirm_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Correcto", callback_data='trade_si'),
            InlineKeyboardButton("❌ Incorrecto", callback_data='trade_no'),
        ]
    ])

def emocion_trade_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f'trade_emo_{key}')]
        for key, label in EMOCIONES_TRADE
    ])

def estrategia_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sí, seguí el plan", callback_data='trade_plan_si'),
            InlineKeyboardButton("❌ Me salí del plan",  callback_data='trade_plan_no'),
        ]
    ])

# ------------------------------------
# STORAGE
# ------------------------------------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
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
    return {
        "registros": [], "chat_id": None, "flow": None, "esperando": None,
        "gastos": [], "habitos": [], "habito_flow": None,
        "ai_history": [], "ai_last_message": None, "pending_action": None,
        "trades": [], "notas": [], "trade_pending": None, "trade_fotos": [],
        "recordatorios": [], "pasos": [], "calorias": [], "meta_calorias": META_CAL_BASE,
    }

def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

def guardar_registro(tipo, respuesta):
    data = load_data()
    data["registros"].append({
        "tipo": tipo,
        "fecha": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "respuesta": respuesta,
    })
    data["flow"] = None; data["esperando"] = None; save_data(data)

def registrar_gasto(cantidad, categoria, descripcion=None, comercio=None):
    cat = CATEGORIAS_ALIAS.get(categoria.lower(), categoria.lower()) if categoria else None
    data = load_data()
    entry = {
        "fecha":    datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "cantidad": float(cantidad),
        "categoria": cat,
    }
    if descripcion:
        entry["descripcion"] = descripcion
    if comercio:
        entry["comercio"] = comercio
    data["gastos"].append(entry)
    save_data(data)
    return cat

def registrar_ingreso(cantidad, tipo, descripcion=None):
    data = load_data()
    if "ingresos" not in data:
        data["ingresos"] = []
    data["ingresos"].append({
        "fecha":    datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "cantidad": float(cantidad),
        "tipo":     tipo,
        "descripcion": descripcion or "",
    })
    save_data(data)

def registrar_movimiento(cantidad, descripcion):
    data = load_data()
    if "movimientos" not in data:
        data["movimientos"] = []
    data["movimientos"].append({
        "fecha":    datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "cantidad": float(cantidad),
        "descripcion": descripcion,
    })
    save_data(data)

def check_budget_alert(categoria):
    presup = PRESUPUESTO.get(categoria)
    if not presup:
        return None
    total = sum(g["cantidad"] for g in get_gastos_mes() if g["categoria"] == categoria)
    pct = total / presup * 100
    if pct >= 100:
        return f"🚨 *¡Superaste el presupuesto de {escape_md(categoria.capitalize())}\\!*\n_${total:.0f} de ${presup} \\({pct:.0f}%\\)_"
    elif pct >= 80:
        return f"⚠️ *Alerta: {escape_md(categoria.capitalize())} al {pct:.0f}%*\n_${total:.0f} de ${presup}_"
    return None

def get_gastos_mes(año=None, mes=None):
    now = datetime.now(TIMEZONE)
    año = año or now.year; mes = mes or now.month
    return [
        g for g in load_data().get("gastos", [])
        if g["fecha"].startswith(f"{año:04d}-{mes:02d}")
    ]

def get_habitos_dias(n=7):
    cutoff = (datetime.now(TIMEZONE).date() - timedelta(days=n - 1))
    return [
        h for h in load_data().get("habitos", [])
        if datetime.strptime(h["fecha"], "%Y-%m-%d").date() >= cutoff
    ]

def get_streak(clave):
    habitos_sorted = sorted(load_data().get("habitos", []), key=lambda h: h["fecha"], reverse=True)
    if not habitos_sorted:
        return 0
    streak = 0
    expected = None
    for h in habitos_sorted:
        hdate = datetime.strptime(h["fecha"], "%Y-%m-%d").date()
        if expected is None:
            expected = hdate
        if hdate == expected:
            if h["respuestas"].get(clave):
                streak += 1
                expected = hdate - timedelta(days=1)
            else:
                break
        elif hdate < expected:
            break
    return streak

def get_streaks():
    return {clave: get_streak(clave) for clave, _ in HABITOS}

def get_habitos_mes(año=None, mes=None):
    now = datetime.now(TIMEZONE)
    año = año or now.year
    mes = mes or now.month
    prefix = f"{año:04d}-{mes:02d}"
    return [h for h in load_data().get("habitos", []) if h["fecha"].startswith(prefix)]

def get_stats_habs(año=None, mes=None):
    habitos = get_habitos_mes(año, mes)
    stats = {clave: 0 for clave, _ in HABITOS}
    for h in habitos:
        for clave, _ in HABITOS:
            if h["respuestas"].get(clave):
                stats[clave] += 1
    stats["total_dias"] = len(habitos)
    return stats

def get_ingresos_mes(año=None, mes=None):
    now = datetime.now(TIMEZONE)
    año = año or now.year
    mes = mes or now.month
    prefix = f"{año:04d}-{mes:02d}"
    return [i for i in load_data().get("ingresos", []) if i["fecha"].startswith(prefix)]

def get_movimientos_mes(año=None, mes=None):
    now = datetime.now(TIMEZONE)
    año = año or now.year
    mes = mes or now.month
    prefix = f"{año:04d}-{mes:02d}"
    return [m for m in load_data().get("movimientos", []) if m["fecha"].startswith(prefix)]

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

def registrar_habito(respuestas):
    data = load_data()
    data["habitos"].append({
        "fecha": datetime.now(TIMEZONE).strftime("%Y-%m-%d"),
        "respuestas": respuestas,
    })
    data["habito_flow"] = None; save_data(data)

def guardar_nota(texto):
    data = load_data()
    data["notas"].append({
        "fecha": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "texto": texto,
    })
    save_data(data)

def get_open_trade():
    trades = load_data().get("trades", [])
    for t in reversed(trades):
        if t.get("fecha_salida") is None:
            return t
    return None

def guardar_trade_entrada(trade_data):
    data = load_data()
    data["trades"].append(trade_data)
    save_data(data)

def cerrar_trade(fecha_entrada, salida, emocion, siguio_plan):
    data = load_data()
    for t in data["trades"]:
        if t.get("fecha_entrada") == fecha_entrada:
            t["fecha_salida"] = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
            t["salida"] = salida
            t["emocion"] = emocion
            t["siguio_plan"] = siguio_plan
            # Calcular resultado en R si hay SL
            try:
                if t.get("sl") and t.get("entrada"):
                    riesgo = abs(float(t["entrada"]) - float(t["sl"]))
                    resultado = float(salida) - float(t["entrada"])
                    if t.get("direccion") == "short":
                        resultado = -resultado
                    t["resultado_r"] = round(resultado / riesgo, 2) if riesgo > 0 else None
            except Exception:
                t["resultado_r"] = None
            break
    save_data(data)

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
    data = load_data(); data["pending_action"] = action; save_data(data)

def get_pending_action():
    return load_data().get("pending_action")

def clear_pending_action():
    data = load_data(); data["pending_action"] = None; save_data(data)

def clear_all_flows():
    data = load_data()
    data["flow"] = None; data["esperando"] = None
    data["habito_flow"] = None; data["pending_action"] = None
    data["trade_pending"] = None
    save_data(data)

# ------------------------------------
# SALUD — PASOS / CALORÍAS
# ------------------------------------

def registrar_pasos(valor: int):
    data = load_data()
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    data["pasos"] = [p for p in data.get("pasos", []) if p["fecha"] != fecha]
    data["pasos"].append({"fecha": fecha, "valor": int(valor)})
    data["pasos"].sort(key=lambda x: x["fecha"])
    save_data(data)

def registrar_calorias(valor: int):
    data = load_data()
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    data["calorias"] = [c for c in data.get("calorias", []) if c["fecha"] != fecha]
    data["calorias"].append({"fecha": fecha, "valor": int(valor)})
    data["calorias"].sort(key=lambda x: x["fecha"])
    save_data(data)

def get_salud_hoy() -> dict:
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    data  = load_data()
    pasos = next((p["valor"] for p in reversed(data.get("pasos", [])) if p["fecha"] == fecha), None)
    cal   = next((c["valor"] for c in reversed(data.get("calorias", [])) if c["fecha"] == fecha), None)
    pesos = data.get("peso", [])
    ultimo_peso = pesos[-1]["valor"] if pesos else None
    meta_cal = data.get("meta_calorias", META_CAL_BASE)
    return {"pasos": pasos, "calorias": cal, "peso": ultimo_peso, "meta_calorias": meta_cal}

def get_salud_semana() -> dict:
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=6)).strftime("%Y-%m-%d")
    data   = load_data()
    pasos_sem  = [p for p in data.get("pasos", []) if p["fecha"] >= cutoff]
    cal_sem    = [c for c in data.get("calorias", []) if c["fecha"] >= cutoff]
    avg_pasos  = round(sum(p["valor"] for p in pasos_sem) / len(pasos_sem)) if pasos_sem else None
    avg_cal    = round(sum(c["valor"] for c in cal_sem) / len(cal_sem)) if cal_sem else None
    return {"avg_pasos": avg_pasos, "avg_calorias": avg_cal,
            "dias_pasos": len(pasos_sem), "dias_calorias": len(cal_sem)}

def es_semana_corte() -> bool:
    """True si este sábado le toca corte (cada 2 semanas desde la base)."""
    base = datetime.strptime(CORTE_CABELLO_BASE, "%Y-%m-%d").date()
    hoy  = datetime.now(TIMEZONE).date()
    diff = (hoy - base).days
    return diff >= 0 and (diff // 7) % 2 == 0

# ------------------------------------
# SOFÍA — MODO PSICÓLOGA
# ------------------------------------

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

# ------------------------------------
# UTILIDADES — helpers
# ------------------------------------

def es_ultimo_viernes():
    today = datetime.now(TIMEZONE).date()
    if today.weekday() != 4:
        return False
    weeks = monthcalendar(today.year, today.month)
    ultimo_viernes = max(w[FRIDAY] for w in weeks if w[FRIDAY] != 0)
    return today.day == ultimo_viernes

def dia_hoy():
    return datetime.now(TIMEZONE).day

async def enviar_pregunta(bot, chat_id, tipo, paso):
    preguntas = PREGUNTAS_SEMANAL if tipo == 'semanal' else PREGUNTAS_MENSUAL
    total = len(preguntas)
    titulo, pregunta = preguntas[paso]
    tipo_label = "RETROALIMENTACIÓN SEMANAL" if tipo == 'semanal' else "REFLEXIÓN MENSUAL"
    texto = (
        f"⚡ *{escape_md(tipo_label)}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"_{escape_md(f'Pregunta {paso+1} de {total}')}_\n\n"
        f"*{escape_md(titulo)}*\n\n"
        f"{escape_md(pregunta)}\n\n"
        f"_Responde con calma\\. Estoy escuchando\\._ 👇"
    )
    await bot.send_message(chat_id, texto, parse_mode='MarkdownV2')

# ------------------------------------
# RESÚMENES
# ------------------------------------

def streak_text(streaks):
    lines = ""
    labels = {clave: label.split("¿")[-1].rstrip("?").strip() if "¿" in label else label
              for clave, label in HABITOS}
    for clave, s in streaks.items():
        if s >= 2:
            lines += f"🔥 {s} días seguidos: {escape_md(labels[clave])}\n"
    return lines

def generar_resumen_semanal():
    habitos_7  = get_habitos_dias(7)
    cutoff     = (datetime.now(TIMEZONE) - timedelta(days=7)).strftime("%Y-%m-%d")
    gastos_7   = [g for g in load_data().get("gastos", []) if g["fecha"][:10] >= cutoff]
    trades_sem = [t for t in load_data().get("trades", [])
                  if t.get("fecha_entrada", "")[:10] >= cutoff and t.get("fecha_salida")]

    habitos_lines = ""
    for clave, label in HABITOS:
        short = label.split("¿")[-1].rstrip("?").strip() if "¿" in label else label
        if habitos_7:
            cumplidos  = sum(1 for h in habitos_7 if h["respuestas"].get(clave))
            icons      = "".join("✅" if h["respuestas"].get(clave) else "❌" for h in habitos_7[-7:])
            streak     = get_streak(clave)
            streak_tag = f" 🔥{streak}" if streak >= 2 else ""
            habitos_lines += f"\\- {escape_md(short)}: {icons} {cumplidos}/{len(habitos_7)}{streak_tag}\n"
        else:
            habitos_lines += f"\\- {escape_md(short)}: _sin datos_\n"

    gastos_por_cat = {}
    for g in gastos_7:
        gastos_por_cat[g["categoria"]] = gastos_por_cat.get(g["categoria"], 0) + g["cantidad"]
    total_g = sum(gastos_por_cat.values())
    gastos_lines = ""
    for cat, total in sorted(gastos_por_cat.items(), key=lambda x: -x[1]):
        gastos_lines += f"\\- {escape_md(cat.capitalize())}: ${total:.0f}\n"
    if not gastos_lines:
        gastos_lines = "_Sin gastos registrados_\n"

    trades_lines = ""
    if trades_sem:
        wins  = sum(1 for t in trades_sem if (t.get("resultado_r") or 0) > 0)
        total_t = len(trades_sem)
        rs    = [t["resultado_r"] for t in trades_sem if t.get("resultado_r") is not None]
        total_r = sum(rs)
        trades_lines = (
            f"\n📈 *Trades de la semana*\n"
            f"\\- Trades: {total_t} \\| Win rate: {wins}/{total_t}\n"
            f"\\- R total: {escape_md(f'{total_r:+.2f}R')}\n"
        )

    # Salud de la semana
    sem_salud = get_salud_semana()
    salud_lines = ""
    if sem_salud["avg_pasos"]:
        pct_pasos = round(sem_salud["avg_pasos"] / META_PASOS_DIARIO * 100)
        icon_p = "✅" if pct_pasos >= 80 else "⚠️"
        salud_lines += f"\\- {icon_p} Pasos prom: {sem_salud['avg_pasos']:,}/día \\({pct_pasos}% meta\\)\n"
    if sem_salud["avg_calorias"]:
        salud_lines += f"\\- 🔥 Cal quemadas prom: {sem_salud['avg_calorias']} kcal/día\n"
    if salud_lines:
        salud_section = f"\n💪 *Salud \\(Samsung Watch\\)*\n{salud_lines}"
    else:
        salud_section = ""

    # Próxima semana en el calendario
    try:
        eventos_7 = _listar_eventos_sync(days_ahead=7)
        if eventos_7:
            # Detectar días cargados (>2 eventos)
            from collections import Counter
            dias_count = Counter()
            for e in eventos_7:
                try:
                    dia = e['inicio'][:10]
                    dias_count[dia] += 1
                except Exception:
                    pass
            dias_cargados = [d for d, n in dias_count.items() if n >= 2]
            cal_lines = ""
            for e in eventos_7[:5]:
                try:
                    if 'T' in e['inicio']:
                        dt = datetime.fromisoformat(e['inicio'].replace('Z', '+00:00')).astimezone(TIMEZONE)
                        when = dt.strftime('%a %d %H:%M')
                    else:
                        when = e['inicio']
                    cal_lines += f"\\- {escape_md(when)}: {escape_md(e['titulo'])}\n"
                except Exception:
                    pass
            if len(eventos_7) > 5:
                cal_lines += f"\\- _\\.\\.\\. y {len(eventos_7)-5} eventos más_\n"
            carga_txt = ""
            if dias_cargados:
                dias_fmt = ", ".join(escape_md(d) for d in dias_cargados[:3])
                carga_txt = f"⚠️ _Días cargados: {dias_fmt}_\n"
            agenda_section = f"\n📅 *Próxima semana \\(calendario\\)*\n{cal_lines}{carga_txt}"
        else:
            agenda_section = ""
    except Exception:
        agenda_section = ""

    return (
        "📊 *RAÚL — RESUMEN DE LA SEMANA*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💪 *Hábitos \\(últimos 7 días\\)*\n{habitos_lines}"
        f"{salud_section}"
        f"{trades_lines}\n"
        f"💰 *Gastos de la semana*\n{gastos_lines}"
        f"Total: ${total_g:.0f}\n"
        f"{agenda_section}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "_Ahora responde honestamente\\. ¿Cómo fue la semana?_ 👇"
    )

def generar_resumen_gastos():
    now = datetime.now(TIMEZONE)
    gastos_mes = get_gastos_mes()
    mes_esc = escape_md(now.strftime('%B %Y').capitalize())
    if not gastos_mes:
        return (
            f"💸 *Gastos de {mes_esc}*\n\n"
            "_Sin gastos registrados aún\\._\n\n"
            "_Escribe:_ `gasto 150 comida`"
        )
    gastos_por_cat = {}
    for g in gastos_mes:
        gastos_por_cat[g["categoria"]] = gastos_por_cat.get(g["categoria"], 0) + g["cantidad"]
    total_gastado = sum(gastos_por_cat.values())
    lines = ""
    for cat in sorted(gastos_por_cat, key=lambda c: -gastos_por_cat[c]):
        gastado = gastos_por_cat[cat]
        presup  = PRESUPUESTO.get(cat)
        cat_esc = escape_md(cat.capitalize())
        if presup:
            pct    = gastado / presup * 100
            status = " ⚠️" if gastado > presup else ""
            lines += f"\\- *{cat_esc}*: ${gastado:.0f} / ${presup}{escape_md(status)} \\({pct:.0f}%\\)\n"
        else:
            lines += f"\\- *{cat_esc}*: ${gastado:.0f}\n"
    return (
        f"💸 *GASTOS — {mes_esc}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{lines}\n"
        f"*Total: ${total_gastado:.0f} / ${sum(PRESUPUESTO.values())}*"
    )

def generar_como_voy():
    now = datetime.now(TIMEZONE)
    data = load_data()
    num_semanas = len([r for r in data.get("registros", []) if r["tipo"] == "semanal"])
    habitos_7   = get_habitos_dias(7)
    streaks     = get_streaks()

    habitos_lines = ""
    for clave, label in HABITOS:
        short = label.split("¿")[-1].rstrip("?").strip() if "¿" in label else label
        s = streaks.get(clave, 0)
        streak_tag = f" 🔥 {s} días" if s >= 2 else ""
        if habitos_7:
            cumplidos = sum(1 for h in habitos_7 if h["respuestas"].get(clave))
            icons     = "".join("✅" if h["respuestas"].get(clave) else "❌" for h in habitos_7)
            habitos_lines += f"\\- {escape_md(short)}: {icons} {cumplidos}/{len(habitos_7)}{escape_md(streak_tag)}\n"
        else:
            habitos_lines += f"\\- {escape_md(short)}: _sin datos_\n"

    gastos_mes    = get_gastos_mes()
    total_gastado = sum(g["cantidad"] for g in gastos_mes)
    gastos_por_cat = {}
    for g in gastos_mes:
        gastos_por_cat[g["categoria"]] = gastos_por_cat.get(g["categoria"], 0) + g["cantidad"]
    gastos_lines = ""
    for cat in sorted(gastos_por_cat, key=lambda c: -gastos_por_cat[c]):
        gastado = gastos_por_cat[cat]
        presup  = PRESUPUESTO.get(cat)
        cat_esc = escape_md(cat.capitalize())
        status  = " ⚠️" if presup and gastado > presup else ""
        pct_txt = f" \\({gastado/presup*100:.0f}%\\)" if presup else ""
        gastos_lines += f"  \\- {cat_esc}: ${gastado:.0f}{escape_md(status)}{pct_txt}\n"
    if not gastos_lines:
        gastos_lines = "  _Sin gastos este mes_\n"

    # Trades resumen del mes
    trades_mes = [t for t in data.get("trades", [])
                  if t.get("fecha_entrada", "")[:7] == now.strftime("%Y-%m") and t.get("fecha_salida")]
    trades_line = ""
    if trades_mes:
        wins  = sum(1 for t in trades_mes if (t.get("resultado_r") or 0) > 0)
        rs    = [t["resultado_r"] for t in trades_mes if t.get("resultado_r") is not None]
        total_r = sum(rs)
        trades_line = (
            f"\n📈 *Trades del mes*\n"
            f"  \\- {len(trades_mes)} trades \\| {wins} ganados\n"
            f"  \\- R total: {escape_md(f'{total_r:+.2f}R')}\n"
        )

    mes_esc = escape_md(now.strftime('%B').capitalize())
    return (
        f"🎯 *RAÚL — ¿CÓMO VAS?*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 *Semanas registradas:* {num_semanas}\n\n"
        f"💪 *Hábitos \\(últimos 7 días\\)*\n{habitos_lines}"
        f"{trades_line}\n"
        f"💸 *Gastos de {mes_esc}*\n{gastos_lines}\n"
        f"*Total gastado: ${total_gastado:.0f} / ${sum(PRESUPUESTO.values())}*"
    )

def _build_salud_mensual(año: int, mes: int) -> str:
    """Sección salud para el reporte mensual."""
    prefix = f"{año:04d}-{mes:02d}"
    data   = load_data()
    pasos_mes = [p for p in data.get("pasos", []) if p["fecha"].startswith(prefix)]
    cal_mes   = [c for c in data.get("calorias", []) if c["fecha"].startswith(prefix)]
    pesos     = data.get("peso", [])

    if not pasos_mes and not cal_mes:
        return ""

    lines = ["💚 *SALUD & FITNESS*\n"]
    if pasos_mes:
        avg_p = round(sum(p["valor"] for p in pasos_mes) / len(pasos_mes))
        dias_meta = sum(1 for p in pasos_mes if p["valor"] >= META_PASOS_DIARIO)
        icon_p = "✅" if avg_p >= META_PASOS_DIARIO * 0.8 else "⚠️"
        lines.append(f"  {icon_p} Pasos: promedio {avg_p:,}/día \\| días con meta: {dias_meta}\n")
    if cal_mes:
        avg_c = round(sum(c["valor"] for c in cal_mes) / len(cal_mes))
        lines.append(f"  🔥 Calorías quemadas: {avg_c} kcal/día promedio\n")
    if pesos:
        ultimo = pesos[-1]["valor"]
        lines.append(f"  ⚖️ Peso actual: {ultimo:.1f} kg \\| Meta cal: {data.get('meta_calorias', META_CAL_BASE)} kcal/día\n")
    lines.append("\n")
    return "".join(lines)

def generar_reporte_global_mensual(año=None, mes=None):
    """Reporte completo del mes: finanzas + hábitos + fotos + coach."""
    now = datetime.now(TIMEZONE)
    año = año or now.year
    mes = mes or now.month
    # Si es día 1, reportamos el mes anterior
    if now.day == 1 and año == now.year and mes == now.month:
        if mes == 1:
            año -= 1; mes = 12
        else:
            mes -= 1

    import calendar
    nombre_mes = calendar.month_name[mes]
    mes_esc = escape_md(f"{nombre_mes} {año}")

    # --- FINANZAS ---
    gastos_mes    = get_gastos_mes(año, mes)
    ingresos_mes  = get_ingresos_mes(año, mes)
    movs_mes      = get_movimientos_mes(año, mes)

    total_ingresos   = sum(i["cantidad"] for i in ingresos_mes)
    total_gastos     = sum(g["cantidad"] for g in gastos_mes)
    total_movs       = sum(m["cantidad"] for m in movs_mes)
    balance          = total_ingresos - total_gastos

    gastos_por_cat = {}
    for g in gastos_mes:
        cat = g.get("categoria") or "otros"
        gastos_por_cat[cat] = gastos_por_cat.get(cat, 0) + g["cantidad"]

    ingresos_por_tipo = {}
    for i in ingresos_mes:
        t = i.get("tipo") or "otro"
        ingresos_por_tipo[t] = ingresos_por_tipo.get(t, 0) + i["cantidad"]

    lineas_gastos = ""
    for cat, total in sorted(gastos_por_cat.items(), key=lambda x: -x[1]):
        presup = PRESUPUESTO.get(cat)
        cat_e  = escape_md(cat.capitalize())
        if presup:
            pct = total / presup * 100
            warn = " ⚠️" if total > presup else ""
            lineas_gastos += f"  \\- {cat_e}: ${total:.0f}/{presup}{escape_md(warn)} \\({pct:.0f}%\\)\n"
        else:
            lineas_gastos += f"  \\- {cat_e}: ${total:.0f}\n"
    if not lineas_gastos:
        lineas_gastos = "  _Sin gastos registrados_\n"

    lineas_ingresos = ""
    for t, total in sorted(ingresos_por_tipo.items(), key=lambda x: -x[1]):
        lineas_ingresos += f"  \\- {escape_md(t.capitalize())}: ${total:.0f}\n"
    if not lineas_ingresos:
        lineas_ingresos = "  _Sin ingresos registrados_\n"

    balance_e = escape_md(f"${balance:+,.0f}")
    balance_icon = "✅" if balance >= 0 else "🔴"

    movs_line = f"  🔄 Transferencias entre cuentas: ${total_movs:.0f}\n" if total_movs > 0 else ""

    # --- HÁBITOS ---
    stats = get_stats_habs(año, mes)
    total_dias = stats["total_dias"]
    gym_dias      = stats.get("gym", 0)
    comida_dias   = stats.get("comida_casa", 0)
    trading_dias  = stats.get("trading_plan", 0)

    meta_gym = 20  # meta mensual de gym
    gym_pct  = gym_dias / meta_gym * 100 if meta_gym else 0
    gym_icon = "✅" if gym_dias >= meta_gym * 0.8 else "⚠️" if gym_dias >= meta_gym * 0.5 else "🔴"

    # Semanas en el mes (promedio semanal)
    semanas = total_dias / 7 if total_dias >= 7 else 1
    gym_sem = round(gym_dias / semanas, 1) if semanas else gym_dias

    comida_pct = round(comida_dias / total_dias * 100) if total_dias else 0
    comida_icon = "✅" if comida_pct >= 80 else "⚠️" if comida_pct >= 50 else "🔴"

    # --- FOTOS / TRADES ---
    data  = load_data()
    prefix_fotos = f"{año:04d}-{mes:02d}"
    fotos_mes = [f for f in data.get("trade_fotos", []) if f["fecha"].startswith(prefix_fotos)]

    trades_mes = [t for t in data.get("trades", [])
                  if t.get("fecha_entrada", "")[:7] == f"{año:04d}-{mes:02d}" and t.get("fecha_salida")]
    trades_line = ""
    if trades_mes:
        wins    = sum(1 for t in trades_mes if (t.get("resultado_r") or 0) > 0)
        rs      = [t["resultado_r"] for t in trades_mes if t.get("resultado_r") is not None]
        total_r = sum(rs)
        wrate   = round(wins / len(trades_mes) * 100)
        r_icon  = "✅" if total_r > 0 else "🔴"
        trades_line = (
            f"\n📈 *Trades del mes*\n"
            f"  \\- Operaciones: {len(trades_mes)} \\| Win rate: {wrate}% \\({wins}/{len(trades_mes)}\\)\n"
            f"  \\- R acumulado: {r_icon} {escape_md(f'{total_r:+.2f}R')}\n"
        )

    # --- COACH OBSERVATIONS ---
    obs = []
    if gym_dias < 10 and total_dias >= 15:
        obs.append(f"💪 Solo fuiste {gym_dias} días al gym este mes\\. Tu cuerpo necesita más constancia\\.")
    if comida_pct < 60 and total_dias >= 15:
        obs.append(f"🍽 Comiste en casa solo {comida_pct}% de los días\\. Estás gastando de más en comida de la calle\\.")
    if total_gastos > total_ingresos and total_ingresos > 0:
        obs.append(f"⚠️ Gastaste más de lo que ingresaste este mes\\. Revisión necesaria\\.")
    gasto_cap = gastos_por_cat.get("capricho", 0)
    if gasto_cap > PRESUPUESTO.get("capricho", 500):
        obs.append(f"🎯 Caprichos/impulsos: ${gasto_cap:.0f} \\(sobre presupuesto\\)\\. ¿Qué disparó eso?")
    if not obs:
        obs.append("Todo va bien — sin alertas críticas este mes\\.")

    obs_text = "\n".join(f"  {o}" for o in obs)

    return (
        f"📊 *RAÚL — REPORTE GLOBAL: {mes_esc}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *FINANZAS*\n"
        f"{lineas_ingresos}"
        f"  _Total ingresos: ${total_ingresos:,.0f}_\n\n"
        f"💸 *GASTOS*\n"
        f"{lineas_gastos}"
        f"  _Total gastos: ${total_gastos:,.0f}_\n"
        f"{movs_line}"
        f"  {balance_icon} *Balance: {balance_e}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💪 *HÁBITOS*\n"
        f"  {gym_icon} Gym: {gym_dias} días \\({escape_md(str(gym_sem))} días/semana en promedio\\)\n"
        f"  {comida_icon} Comida en casa: {comida_dias} días \\({comida_pct}%\\)\n"
        f"  📈 Trading según plan: {trading_dias} días\n"
        f"  📅 Check\\-ins registrados: {total_dias} días\n"
        f"{trades_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📸 *ARCHIVO*\n"
        f"  Fotos guardadas este mes: {len(fotos_mes)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{_build_salud_mensual(año, mes)}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧠 *OBSERVACIONES DEL COACH*\n"
        f"{obs_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Este es tu espejo del mes\\. ¿Qué ves?_"
    )


def _generar_reporte_sofia_mensual_sync(año=None, mes=None) -> str:
    """Llama a Groq para generar el análisis emocional mensual de Sofía."""
    data = load_data()
    history = data.get("sofia_history", [])
    if not history:
        return None

    now = datetime.now(TIMEZONE)
    año = año or now.year
    mes = mes or now.month
    if now.day == 1 and año == now.year and mes == now.month:
        if mes == 1: año -= 1; mes = 12
        else: mes -= 1

    import calendar
    nombre_mes = calendar.month_name[mes]

    # Filtrar mensajes del mes en cuestión si tienen fecha, o usar todos
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    if not user_msgs:
        return None

    resumen_conversaciones = "\n".join(f"- {m[:200]}" for m in user_msgs[-60:])

    prompt = f"""Eres Sofía, la psicóloga de Raúl. Tienes acceso a lo que te platicó durante {nombre_mes} {año}.

MENSAJES DEL USUARIO EN SESIONES PASADAS:
{resumen_conversaciones}

Genera un reporte mensual de progreso emocional. Incluye:
1. EMOCIONES DOMINANTES: ¿qué emociones aparecieron más?
2. PATRONES DETECTADOS: ¿qué comportamientos o pensamientos se repiten?
3. LO QUE MEJORÓ: avances reales que notas
4. LO QUE SIGUE PENDIENTE: áreas que necesitan trabajo
5. RECOMENDACIÓN PARA EL MES QUE SIGUE: una cosa concreta a trabajar

Tono: profesional, cálido, honesto. Máximo 20 líneas. Sin markdown. Habla directo a Raúl."""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def _generar_reporte_sofia_anual_sync(año=None) -> str:
    """Genera el análisis emocional anual de Sofía."""
    data = load_data()
    history = data.get("sofia_history", [])
    if not history:
        return None
    now = datetime.now(TIMEZONE)
    año = año or (now.year - 1)
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    if not user_msgs:
        return None
    resumen = "\n".join(f"- {m[:150]}" for m in user_msgs[-100:])
    prompt = f"""Eres Sofía, psicóloga de Raúl. Tienes el historial completo del año {año}.

MUESTRA DE LO QUE PLATICÓ RAÚL ESTE AÑO:
{resumen}

Genera un REPORTE ANUAL EMOCIONAL. Incluye:
1. CÓMO FUE EL AÑO: resumen de eventos emocionales clave
2. CÓMO REACCIONÓ: patrones de respuesta ante la adversidad
3. LO QUE MEJORÓ: crecimiento real
4. LO QUE SIGUE ARRASTRANDO: heridas o patrones no resueltos
5. SITUACIONES IMPORTANTES: momentos clave del año
6. VISIÓN QUE TE FALTÓ: qué perspectiva le habría ayudado a crecer más
7. REFLEXIÓN FINAL: algo que lo ayude a valorar lo que vivió

Máximo 30 líneas. Sin markdown. Tono: honesto, profundo, esperanzador."""
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def _generar_reporte_financiero_anual_sync(año=None) -> str:
    """Genera el análisis financiero anual."""
    now = datetime.now(TIMEZONE)
    año = año or (now.year - 1)
    data = load_data()

    import calendar

    resumen_meses = []
    for mes in range(1, 13):
        gastos   = get_gastos_mes(año, mes)
        ingresos = get_ingresos_mes(año, mes)
        movs     = get_movimientos_mes(año, mes)
        if not gastos and not ingresos:
            continue
        tg = sum(g["cantidad"] for g in gastos)
        ti = sum(i["cantidad"] for i in ingresos)
        bal = ti - tg
        nombre = calendar.month_abbr[mes]
        resumen_meses.append(f"{nombre}: ingresos=${ti:.0f} gastos=${tg:.0f} balance=${bal:+.0f}")

    if not resumen_meses:
        return None

    datos_str = "\n".join(resumen_meses)
    prompt = f"""Analiza las finanzas de Raúl en {año}.

DATOS POR MES:
{datos_str}

Genera un REPORTE FINANCIERO ANUAL. Incluye:
1. RESUMEN GENERAL: total ingresos, gastos, balance del año
2. DISTRIBUCIÓN DE CAPITAL: cómo se distribuyó el dinero
3. MEJORES Y PEORES MESES: con análisis de qué pasó
4. ERRORES Y ACIERTOS: decisiones financieras notables
5. RECOMENDACIONES: 3 cosas concretas para mejorar el manejo del dinero el siguiente año

Máximo 20 líneas. Sin markdown. Directo a Raúl, tono de coach financiero."""
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.5,
    )
    return resp.choices[0].message.content.strip()


def mostrar_registros(registros, titulo):
    if not registros:
        return f"📚 *{escape_md(titulo)}*\n\n_Sin registros aún\\._"
    texto = f"📚 *{escape_md(titulo)}*\n\n"
    for r in reversed(registros[-5:]):
        fecha = escape_md(r['fecha'])
        resp  = escape_md(r['respuesta'][:300])
        texto += f"📅 _{fecha}_\n{resp}\n\n"
    return texto

def mostrar_trades(trades):
    cerrados = [t for t in trades if t.get("fecha_salida")]
    if not cerrados:
        return "📈 *Trades*\n\n_Sin trades cerrados aún\\._"
    texto = "📈 *ÚLTIMOS TRADES*\n━━━━━━━━━━━━━━━\n\n"
    for t in reversed(cerrados[-5:]):
        par   = escape_md(t.get("par", "?"))
        dire  = escape_md(t.get("direccion", "?"))
        ent   = escape_md(str(t.get("entrada", "?")))
        sal   = escape_md(str(t.get("salida", "?")))
        r_val = t.get("resultado_r")
        r_txt = escape_md(f"{r_val:+.2f}R") if r_val is not None else "?"
        emoji = "✅" if (r_val or 0) > 0 else "🔴"
        emo   = escape_md(t.get("emocion", "?"))
        fecha = escape_md(t.get("fecha_entrada", "?")[:10])
        texto += (
            f"{emoji} *{par}* {dire} \\| _{fecha}_\n"
            f"  Entrada: {ent} → Salida: {sal} \\| *{r_txt}*\n"
            f"  Emoción: {emo}\n\n"
        )
    return texto

def mostrar_notas(notas):
    if not notas:
        return "📝 *Notas*\n\n_Sin notas aún\\._\n\nDile al bot algo como:\n_\"recuérdame llamar al contador el martes\"_"
    texto = "📝 *NOTAS GUARDADAS*\n━━━━━━━━━━━━━━━\n\n"
    for n in reversed(notas[-8:]):
        fecha = escape_md(n.get("fecha", "?")[:10])
        nota  = escape_md(n.get("texto", ""))
        texto += f"📅 _{fecha}_\n{nota}\n\n"
    return texto

def mostrar_ingresos_mes():
    now = datetime.now(TIMEZONE)
    ingresos = get_ingresos_mes()
    mes_esc  = escape_md(now.strftime('%B %Y').capitalize())
    if not ingresos:
        return (
            f"📥 *Ingresos — {mes_esc}*\n\n"
            "_Sin ingresos registrados\\._\n\n"
            "_Escribe:_ `ingrese 8000 renta`\n"
            "_O usa Gmail — detecta depósitos automáticamente\\._"
        )
    total = sum(i["cantidad"] for i in ingresos)
    por_tipo = {}
    for i in ingresos:
        t = i.get("tipo") or "otro"
        por_tipo[t] = por_tipo.get(t, 0) + i["cantidad"]
    lineas = ""
    for t, v in sorted(por_tipo.items(), key=lambda x: -x[1]):
        lineas += f"\\- *{escape_md(t.capitalize())}*: ${v:,.0f}\n"
    detalle = ""
    for i in sorted(ingresos, key=lambda x: x["fecha"], reverse=True)[:15]:
        fuente   = "📧" if i.get("descripcion") else "✍️"
        desc_raw = i.get("descripcion", "")[:40]
        tipo_raw = i.get("tipo", "otro") or "otro"
        monto    = escape_md(f"${i['cantidad']:,.0f}")
        fecha    = escape_md(i['fecha'][:10])
        tipo_esc = escape_md(tipo_raw)
        desc_esc = f" \\- {escape_md(desc_raw)}" if desc_raw else ""
        detalle += f"{fuente} {fecha}: *{monto}* _{tipo_esc}_{desc_esc}\n"
    return (
        f"📥 *INGRESOS — {mes_esc}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"*Total: ${total:,.0f}*\n\n"
        f"Por tipo:\n{lineas}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Detalle \\(últimos 15\\):\n{detalle}"
    )

def mostrar_balance_mes():
    now = datetime.now(TIMEZONE)
    mes_esc     = escape_md(now.strftime('%B %Y').capitalize())
    ingresos    = get_ingresos_mes()
    gastos      = get_gastos_mes()
    movimientos = get_movimientos_mes()
    ti = sum(i["cantidad"] for i in ingresos)
    tg = sum(g["cantidad"] for g in gastos)
    tm = sum(m["cantidad"] for m in movimientos)
    balance = ti - tg
    icon    = "✅" if balance >= 0 else "🔴"
    bal_esc = escape_md(f"${balance:+,.0f}")
    # Gastos por categoría
    cat = {}
    for g in gastos:
        c = g.get("categoria") or "otros"
        cat[c] = cat.get(c, 0) + g["cantidad"]
    cat_lines = ""
    for c, v in sorted(cat.items(), key=lambda x: -x[1]):
        presup = PRESUPUESTO.get(c)
        pct_txt = f" \\({v/presup*100:.0f}%\\)" if presup else ""
        warn    = " ⚠️" if presup and v > presup else ""
        cat_lines += f"  \\- {escape_md(c.capitalize())}: ${v:,.0f}{pct_txt}{escape_md(warn)}\n"
    mov_line = f"\n🔄 Movimientos entre cuentas: ${tm:,.0f}\n" if tm else ""
    return (
        f"⚖️ *BALANCE — {mes_esc}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📥 Ingresos:  *${ti:,.0f}*\n"
        f"💸 Gastos:    *${tg:,.0f}*\n"
        f"{mov_line}"
        f"━━━━━━━━━━━━━━━\n"
        f"{icon} Balance: *{bal_esc}*\n\n"
        f"Gastos por categoría:\n{cat_lines if cat_lines else '  _Sin gastos aún_'}"
    )

def mostrar_movimientos_mes():
    now  = datetime.now(TIMEZONE)
    movs = get_movimientos_mes()
    mes_esc = escape_md(now.strftime('%B %Y').capitalize())
    if not movs:
        return (
            f"🔄 *Movimientos — {mes_esc}*\n\n"
            "_Sin movimientos entre cuentas\\._\n\n"
            "_Ejemplo:_ `moví 2000 a CETES`"
        )
    total = sum(m["cantidad"] for m in movs)
    lineas = ""
    for m in sorted(movs, key=lambda x: x["fecha"], reverse=True)[:15]:
        desc = escape_md(m.get("descripcion", "")[:50])
        lineas += f"\\- {escape_md(m['fecha'][:10])}: *${m['cantidad']:,.0f}* — _{desc}_\n"
    return (
        f"🔄 *MOVIMIENTOS — {mes_esc}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"Total movido: *${total:,.0f}*\n\n"
        f"{lineas}"
    )

def mostrar_stats_trading():
    data = load_data()
    now  = datetime.now(TIMEZONE)
    trades_mes = [t for t in data.get("trades", [])
                  if t.get("fecha_entrada", "")[:7] == now.strftime("%Y-%m") and t.get("fecha_salida")]
    trades_todo = [t for t in data.get("trades", []) if t.get("fecha_salida")]
    def _stats(trades, label):
        if not trades:
            return f"  {label}: sin datos\n"
        wins = sum(1 for t in trades if (t.get("resultado_r") or 0) > 0)
        rs   = [t["resultado_r"] for t in trades if t.get("resultado_r") is not None]
        wr   = round(wins / len(trades) * 100) if trades else 0
        return (
            f"  {label}: {len(trades)} trades \\| WR: {wr}% \\({wins}/{len(trades)}\\)\n"
            f"  R acumulado: {escape_md(f'{sum(rs):+.2f}R') if rs else '?'}\n"
        )
    mes_esc = escape_md(now.strftime('%B %Y').capitalize())
    return (
        f"🎯 *ESTADÍSTICAS TRADING*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📅 *{mes_esc}*\n{_stats(trades_mes, 'Este mes')}\n"
        f"📊 *Histórico total*\n{_stats(trades_todo, 'Total')}"
    )

def generar_habitos_mes():
    now    = datetime.now(TIMEZONE)
    mes_esc = escape_md(now.strftime('%B %Y').capitalize())
    stats  = get_stats_habs()
    total  = stats.get("total_dias", 0)
    if total == 0:
        return (
            f"💪 *HÁBITOS — {mes_esc}*\n\n"
            "_Sin check\\-ins registrados este mes\\._\n\n"
            "_El check\\-in diario es a las 9pm\\._"
        )
    gym     = stats.get("gym", 0)
    comida  = stats.get("comida_casa", 0)
    trading = stats.get("trading_plan", 0)
    gym_pct    = round(gym / total * 100)
    comida_pct = round(comida / total * 100)
    trd_pct    = round(trading / total * 100)
    gym_icon  = "✅" if gym_pct >= 80 else "⚠️" if gym_pct >= 50 else "🔴"
    com_icon  = "✅" if comida_pct >= 80 else "⚠️" if comida_pct >= 50 else "🔴"
    trd_icon  = "✅" if trd_pct >= 80 else "⚠️" if trd_pct >= 50 else "🔴"
    streaks = get_streaks()
    streak_lines = ""
    for clave, label in HABITOS:
        s = streaks.get(clave, 0)
        short = label.split("¿")[-1].rstrip("?").strip() if "¿" in label else label
        if s >= 2:
            streak_lines += f"  🔥 {escape_md(short)}: {s} días seguidos\n"
    # Detalle ultimos 7 dias
    hab7 = sorted(get_habitos_dias(7), key=lambda h: h["fecha"])
    detalle = ""
    for h in hab7:
        fecha = escape_md(h["fecha"][5:])
        g = "✅" if h["respuestas"].get("gym") else "❌"
        c = "✅" if h["respuestas"].get("comida_casa") else "❌"
        t = "✅" if h["respuestas"].get("trading_plan") else "❌"
        detalle += f"  {fecha}: Gym {g} Comida {c} Trading {t}\n"
    separator_streak = ("━━━━━━━━━━━━━━━\n" + streak_lines + "\n") if streak_lines else "\n"
    detalle_txt = detalle if detalle else "  _Sin datos_"
    return (
        f"💪 *HÁBITOS — {mes_esc}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"Check\\-ins registrados: *{total} días*\n\n"
        f"{gym_icon} *Gym:* {gym}/{total} días \\({gym_pct}%\\)\n"
        f"{com_icon} *Comida en casa:* {comida}/{total} días \\({comida_pct}%\\)\n"
        f"{trd_icon} *Trading según plan:* {trading}/{total} días \\({trd_pct}%\\)\n"
        f"{separator_streak}"
        f"*Últimos 7 días:*\n{detalle_txt}"
    )

# ------------------------------------
# IA — GROQ CHAT
# ------------------------------------

def _build_historial_compacto() -> str:
    """Resumen compacto de los últimos 3 meses para dar contexto histórico a la IA."""
    now  = datetime.now(TIMEZONE)
    data = load_data()
    lines = []

    # --- Últimos 3 meses: totales por mes ---
    import calendar as _cal
    for delta in range(2, -1, -1):  # mes-2, mes-1, mes actual
        m = now.month - delta
        y = now.year
        while m <= 0:
            m += 12; y -= 1
        nombre = _cal.month_abbr[m]
        gastos_m   = get_gastos_mes(y, m)
        ingresos_m = get_ingresos_mes(y, m)
        tg = sum(g["cantidad"] for g in gastos_m)
        ti = sum(i["cantidad"] for i in ingresos_m)
        if tg or ti:
            lines.append(f"  {nombre} {y}: ingresos=${ti:.0f} gastos=${tg:.0f} balance=${ti-tg:+.0f}")

    # --- Hábitos últimos 30 días ---
    cutoff30 = (now - timedelta(days=29)).strftime("%Y-%m-%d")
    hab30 = [h for h in data.get("habitos", []) if h["fecha"] >= cutoff30]
    if hab30:
        gym30      = sum(1 for h in hab30 if h["respuestas"].get("gym"))
        comida30   = sum(1 for h in hab30 if h["respuestas"].get("comida_casa"))
        trading30  = sum(1 for h in hab30 if h["respuestas"].get("trading_plan"))
        lines.append(f"  Hábitos últimos 30 días ({len(hab30)} registros): gym={gym30} comida_casa={comida30} trading_plan={trading30}")

    # --- Hábitos últimos 7 días (detalle) ---
    cutoff7 = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    hab7 = [h for h in data.get("habitos", []) if h["fecha"] >= cutoff7]
    if hab7:
        detalle = []
        for h in sorted(hab7, key=lambda x: x["fecha"]):
            d_str = h["fecha"][5:]  # MM-DD
            gym_ok = "G" if h["respuestas"].get("gym") else "-"
            com_ok = "C" if h["respuestas"].get("comida_casa") else "-"
            tra_ok = "T" if h["respuestas"].get("trading_plan") else "-"
            detalle.append(f"{d_str}:{gym_ok}{com_ok}{tra_ok}")
        lines.append(f"  Hábitos 7d (G=gym C=comida T=trading): {' '.join(detalle)}")

    # --- Trades últimos 30 días ---
    trades30 = [t for t in data.get("trades", [])
                if t.get("fecha_entrada", "") >= cutoff30 and t.get("fecha_salida")]
    if trades30:
        wins = sum(1 for t in trades30 if (t.get("resultado_r") or 0) > 0)
        rs   = [t["resultado_r"] for t in trades30 if t.get("resultado_r") is not None]
        lines.append(f"  Trades 30d: {len(trades30)} operaciones | {wins} ganadoras | R acum={sum(rs):+.2f}")

    # --- Gastos por categoría últimos 30 días ---
    gastos30 = [g for g in data.get("gastos", []) if g["fecha"][:10] >= cutoff30]
    if gastos30:
        cat30 = {}
        for g in gastos30:
            cat30[g["categoria"]] = cat30.get(g["categoria"], 0) + g["cantidad"]
        cat_str = " | ".join(f"{k}=${v:.0f}" for k, v in sorted(cat30.items(), key=lambda x: -x[1]))
        lines.append(f"  Gastos 30d por categoría: {cat_str}")

    # --- Ingresos últimos 30 días ---
    ingresos30 = [i for i in data.get("ingresos", []) if i["fecha"][:10] >= cutoff30]
    if ingresos30:
        ti30 = sum(i["cantidad"] for i in ingresos30)
        tipos = {}
        for i in ingresos30:
            tipos[i.get("tipo", "otro")] = tipos.get(i.get("tipo", "otro"), 0) + i["cantidad"]
        tipos_str = " | ".join(f"{k}=${v:.0f}" for k, v in tipos.items())
        lines.append(f"  Ingresos 30d: ${ti30:.0f} ({tipos_str})")

    # --- Peso últimos registros ---
    pesos = data.get("peso", [])[-5:]
    if pesos:
        peso_str = " → ".join(f"{p['fecha'][5:]}: {p['valor']:.1f}kg" for p in pesos)
        lines.append(f"  Peso reciente: {peso_str}")

    return "\n".join(lines) if lines else "  Sin historial disponible."


def _consultar_rango(modulo: str, fecha_ini: str, fecha_fin: str) -> str:
    """Extrae datos de un módulo en un rango de fechas y los devuelve como texto para la IA."""
    data = load_data()
    lines = [f"DATOS CONSULTADOS — {modulo.upper()} ({fecha_ini} → {fecha_fin}):"]

    if modulo in ("gastos", "finanzas", "todo"):
        gastos = [g for g in data.get("gastos", [])
                  if fecha_ini <= g["fecha"][:10] <= fecha_fin]
        total = sum(g["cantidad"] for g in gastos)
        cat = {}
        for g in gastos:
            cat[g["categoria"]] = cat.get(g["categoria"], 0) + g["cantidad"]
        lines.append(f"  Gastos: ${total:.0f} en {len(gastos)} movimientos")
        for k, v in sorted(cat.items(), key=lambda x: -x[1]):
            lines.append(f"    {k}: ${v:.0f}")
        for g in sorted(gastos, key=lambda x: x["fecha"])[-20:]:
            lines.append(f"    {g['fecha'][:10]}: ${g['cantidad']:.0f} {g.get('categoria','')} {g.get('descripcion','')[:40]}")

    if modulo in ("ingresos", "finanzas", "todo"):
        ingresos = [i for i in data.get("ingresos", [])
                    if fecha_ini <= i["fecha"][:10] <= fecha_fin]
        total_i = sum(i["cantidad"] for i in ingresos)
        lines.append(f"  Ingresos: ${total_i:.0f} en {len(ingresos)} movimientos")
        for i in sorted(ingresos, key=lambda x: x["fecha"]):
            lines.append(f"    {i['fecha'][:10]}: ${i['cantidad']:.0f} ({i.get('tipo','')} {i.get('descripcion','')[:40]})")

    if modulo in ("habitos", "todo"):
        habitos = [h for h in data.get("habitos", [])
                   if fecha_ini <= h["fecha"] <= fecha_fin]
        gym = sum(1 for h in habitos if h["respuestas"].get("gym"))
        comida = sum(1 for h in habitos if h["respuestas"].get("comida_casa"))
        trading = sum(1 for h in habitos if h["respuestas"].get("trading_plan"))
        lines.append(f"  Hábitos: {len(habitos)} registros | gym={gym} | comida_casa={comida} | trading_plan={trading}")
        for h in sorted(habitos, key=lambda x: x["fecha"]):
            r = h["respuestas"]
            gym_s = "✓" if r.get("gym") else "✗"
            com_s = "✓" if r.get("comida_casa") else "✗"
            tra_s = "✓" if r.get("trading_plan") else "✗"
            lines.append(f"    {h['fecha']}: gym={gym_s} comida={com_s} trading={tra_s}")

    if modulo in ("trades", "todo"):
        trades = [t for t in data.get("trades", [])
                  if fecha_ini <= t.get("fecha_entrada", "")[:10] <= fecha_fin
                  and t.get("fecha_salida")]
        wins = sum(1 for t in trades if (t.get("resultado_r") or 0) > 0)
        rs   = [t["resultado_r"] for t in trades if t.get("resultado_r") is not None]
        lines.append(f"  Trades: {len(trades)} | wins={wins} | R acum={sum(rs):+.2f}")
        for t in sorted(trades, key=lambda x: x.get("fecha_entrada", "")):
            r = t.get("resultado_r")
            lines.append(f"    {t.get('fecha_entrada','')[:10]}: {t.get('par','?')} {t.get('direccion','?')} {f'{r:+.2f}R' if r else '?'} emo={t.get('emocion','?')}")

    if modulo in ("peso", "salud", "todo"):
        pesos = [p for p in data.get("peso", []) if fecha_ini <= p["fecha"] <= fecha_fin]
        if pesos:
            lines.append(f"  Peso: {len(pesos)} registros")
            for p in pesos:
                lines.append(f"    {p['fecha']}: {p['valor']:.1f} kg")
        pasos = [p for p in data.get("pasos", []) if fecha_ini <= p["fecha"] <= fecha_fin]
        if pasos:
            avg = round(sum(p["valor"] for p in pasos) / len(pasos))
            lines.append(f"  Pasos: promedio {avg:,}/día ({len(pasos)} días registrados)")

    if len(lines) == 1:
        lines.append("  Sin datos en ese rango.")

    return "\n".join(lines)


def _build_salud_context() -> str:
    s = get_salud_hoy()
    lines = []
    if s["peso"]:
        lines.append(f"  Peso: {s['peso']:.1f} kg | Meta calorías: {s['meta_calorias']} kcal/día")
    pasos_txt = f"{s['pasos']:,}" if s["pasos"] else "no registrado"
    cal_txt   = f"{s['calorias']} kcal" if s["calorias"] else "no registrado"
    meta_p    = META_PASOS_DIARIO
    pasos_pct = f" ({round(s['pasos']/meta_p*100)}% meta)" if s["pasos"] else ""
    lines.append(f"  Pasos hoy: {pasos_txt}{pasos_pct} | Calorías quemadas: {cal_txt}")
    return "\n".join(lines) if lines else "  Sin datos de salud hoy."

def build_system_prompt():
    now         = datetime.now(TIMEZONE)
    data        = load_data()
    gastos_mes  = get_gastos_mes()
    habitos_7   = get_habitos_dias(7)
    streaks     = get_streaks()
    num_semanas = len([r for r in data.get("registros", []) if r["tipo"] == "semanal"])

    gastos_por_cat = {}
    for g in gastos_mes:
        gastos_por_cat[g["categoria"]] = gastos_por_cat.get(g["categoria"], 0) + g["cantidad"]

    habitos_resumen = {}
    for clave, _ in HABITOS:
        if habitos_7:
            cumplidos = sum(1 for h in habitos_7 if h["respuestas"].get(clave))
            habitos_resumen[clave] = f"{cumplidos}/{len(habitos_7)} | streak: {streaks.get(clave,0)} días"
        else:
            habitos_resumen[clave] = "sin datos"

    # Últimos 10 gastos individuales
    gastos_recientes = sorted(data.get("gastos", []), key=lambda g: g["fecha"], reverse=True)[:10]
    gastos_str = "\n".join([f"  {g['fecha'][:10]}: ${g['cantidad']:.0f} {g['categoria']}"
                             for g in gastos_recientes]) or "  ninguno"

    # Últimas notas
    notas = data.get("notas", [])[-5:]
    notas_str = "\n".join([f"  {n['fecha'][:10]}: {n['texto']}" for n in notas]) or "  ninguna"

    # Trades recientes
    trades_cerrados = [t for t in data.get("trades", []) if t.get("fecha_salida")][-5:]
    trades_str = ""
    if trades_cerrados:
        for t in trades_cerrados:
            r = t.get("resultado_r")
            trades_str += f"  {t.get('fecha_entrada','')[:10]}: {t.get('par','?')} {t.get('direccion','?')} → {f'{r:+.2f}R' if r else '?'}\n"
    else:
        trades_str = "  ninguno aún"

    open_trade = get_open_trade()
    open_str = f"  Tiene un trade abierto en {open_trade.get('par','?')} {open_trade.get('direccion','?')} desde {open_trade.get('fecha_entrada','?')[:10]}" if open_trade else "  ninguno"

    # Ingresos y movimientos del mes
    stats_habs     = get_stats_habs()
    ingresos_mes   = get_ingresos_mes()
    movimientos_mes = get_movimientos_mes()
    total_ingresos = sum(i["cantidad"] for i in ingresos_mes)
    total_movs     = sum(m["cantidad"] for m in movimientos_mes)
    total_gastos_mes = sum(gastos_por_cat.values())
    balance_mes    = total_ingresos - total_gastos_mes

    ingresos_str   = "\n".join([f"  {i['fecha'][:10]}: ${i['cantidad']:.0f} ({i.get('tipo','')})"
                                 for i in ingresos_mes[-5:]]) or "  ninguno"
    movs_str       = "\n".join([f"  {m['fecha'][:10]}: ${m['cantidad']:.0f} ({m.get('descripcion','')})"
                                 for m in movimientos_mes[-5:]]) or "  ninguno"

    # Alertas coach
    coach_alerts = []
    gym_dias   = stats_habs.get("gym", 0)
    total_dias = stats_habs.get("total_dias", 0)
    comida_dias = stats_habs.get("comida_casa", 0)
    if total_dias >= 7:
        gym_sem = gym_dias / (total_dias / 7)
        if gym_sem < 3:
            coach_alerts.append(f"ALERTA GYM: solo {gym_dias} días de gym este mes ({gym_sem:.1f}/semana). Meta: ≥3/semana.")
        comida_pct = comida_dias / total_dias * 100
        if comida_pct < 60:
            coach_alerts.append(f"ALERTA COMIDA: solo {comida_pct:.0f}% comiendo en casa. Gasto innecesario.")
    if total_gastos_mes > total_ingresos > 0:
        coach_alerts.append(f"ALERTA FINANZAS: gastos (${total_gastos_mes:.0f}) > ingresos (${total_ingresos:.0f}) este mes.")
    cap_gasto = gastos_por_cat.get("capricho", 0)
    if cap_gasto > PRESUPUESTO.get("capricho", 500) * 1.2:
        coach_alerts.append(f"ALERTA CAPRICHOS: ${cap_gasto:.0f} en caprichos (sobre presupuesto).")

    coach_str = "\n".join(coach_alerts) if coach_alerts else "  Sin alertas activas."

    historial_compacto = _build_historial_compacto()

    return f"""Eres el asistente personal de Raúl — su coach de vida, entrenador y checador de plenitud integrado en Telegram.

PERFIL DE RAÚL:
- Trader activo, usa estrategia Mark Jeffrey
- Testigo de Jehová, comprometido con su fe
- Vive con su abuelo, lo cuida
- Renta mensual fija: $8,000 pesos
- TikToker y creador de contenido
- Novia: Nallelita
- Trabaja activamente en disciplinarse: hábitos, dinero y trading

CONTEXTO ACTUAL ({now.strftime('%d/%m/%Y %H:%M')} Ciudad de México):
- Semanas de retroalimentación: {num_semanas}

HISTORIAL COMPACTO (últimos 3 meses + detalle 30 días):
{historial_compacto}

FINANZAS DEL MES:
- Gastos por categoría: {json.dumps(gastos_por_cat, ensure_ascii=False) if gastos_por_cat else 'ninguno'}
- Total gastos: ${total_gastos_mes:.0f} | Ingresos: ${total_ingresos:.0f} | Balance: ${balance_mes:+.0f}
- Últimos ingresos:
{ingresos_str}
- Movimientos entre cuentas:
{movs_str}
- Últimos gastos:
{gastos_str}

HÁBITOS ESTE MES (días registrados: {total_dias}):
  gym: {gym_dias} días | {habitos_resumen.get('gym','sin datos')} (últimos 7 días)
  comida en casa: {comida_dias} días | {habitos_resumen.get('comida_casa','sin datos')} (últimos 7 días)
  trading según plan: {stats_habs.get('trading_plan',0)} días | {habitos_resumen.get('trading_plan','sin datos')} (últimos 7 días)

TRADES:
- Abierto: {open_str}
- Recientes:
{trades_str}

NOTAS:
{notas_str}

AGENDA 48H:
{get_calendar_context()}

ALERTAS DEL COACH:
{coach_str}

SALUD HOY (Samsung Watch):
{_build_salud_context()}

INSTRUCCIONES COMO COACH:
- Habla de tú, español mexicano, informal pero directo con carácter
- Eres SU asistente — conoces su vida, sus metas, sus puntos débiles
- Respuestas cortas (3-4 líneas). Sin markdown.
- Si detectas que un área está decayendo, señálalo proactivamente aunque no te pregunte
- Conecta lo que dice con su contexto (trading, fe, abuelo, Nallelita, disciplina)
- NUNCA cuestiones lo que Raúl dice de su vida personal. Acéptalo y ayúdalo.
- Antes de registrar algo importante, puedes hacer UNA pregunta inteligente para clarificar
- Horario scalper: lunes a viernes 7-10am. Análisis semanal: viernes 12:45-1:30pm.
- Rutina gym: lunes, miércoles y viernes.

DETECCIÓN DE ACCIONES — incluye al final (línea separada) si aplica:

Si detectas un GASTO con monto MAYOR A CERO (nunca generes esto si no hay monto explícito):
ACCION_GASTO:[monto]:[categoria]
Categorías: comida, transporte, capricho, salud, otros

Si detectas un INGRESO con monto:
ACCION_INGRESO:[monto]:[tipo]
Tipos: renta, transferencia, rendimientos, otro

Si detectas MOVIMIENTO entre cuentas:
ACCION_MOVIMIENTO:[monto]:[descripcion]

Si quiere guardar una nota:
ACCION_NOTA:[texto]

Si quiere VER agenda:
ACCION_CAL_VER:[dias]

Si quiere CREAR evento:
ACCION_CAL_CREAR:[titulo]|[YYYY-MM-DD]|[HH:MM]|[duracion_minutos]

Si detecta pasos del día (Samsung Watch o manual):
ACCION_PASOS:[numero_entero]

Si detecta calorías quemadas del día:
ACCION_CALORIAS:[numero_entero]

Si el usuario pregunta por datos de un rango de fechas específico que NO tienes disponible (ej: "del 5 al 20 de marzo", "la primera semana de abril"):
ACCION_CONSULTA:[modulo]:[YYYY-MM-DD]:[YYYY-MM-DD]
Módulos: gastos | ingresos | finanzas | habitos | trades | peso | salud | todo

Si necesitas UNA pregunta de clarificación ANTES de registrar algo (solo para info importante/ambigua):
ACCION_RAZONAR:[pregunta concreta y específica]

IMPORTANTE — razonamiento con datos:
- Ya tienes el historial compacto de los últimos 3 meses en el prompt.
- Si preguntan de "esta semana", "hoy", "este mes" o "últimos 30 días" — responde directamente con los datos que ya tienes.
- Solo usa ACCION_CONSULTA cuando necesites datos de un rango específico que no está en el historial compacto.
- Puedes responder preguntas como "¿hice gym esta semana?", "¿cuánto gasté en comida?", "¿cuál fue mi mejor semana?" directamente con los datos del historial.

Solo incluye UNA acción por respuesta y solo si estás muy seguro."""

def _call_groq_sync(user_message: str, history: list) -> str:
    messages = (
        [{"role": "system", "content": build_system_prompt()}]
        + history
        + [{"role": "user", "content": user_message}]
    )
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=400,
    )
    return resp.choices[0].message.content.strip()

async def call_ai(user_message: str, history: list) -> str:
    try:
        return await asyncio.to_thread(_call_groq_sync, user_message, history)
    except Exception as e:
        logger.error(f"Error AI: {e}")
        return "No pude procesar eso ahorita. Intenta de nuevo."

def parse_ai_response(text: str):
    """Devuelve (mensaje_limpio, accion_o_None)."""
    lines  = text.strip().split('\n')
    action = None
    clean  = []
    for line in lines:
        if line.startswith('ACCION_GASTO:'):
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    amt = float(parts[1].strip())
                    if amt > 0:
                        action = {"type": "gasto", "amount": amt, "category": parts[2].strip().lower()}
                except Exception:
                    clean.append(line)
        elif line.startswith('ACCION_INGRESO:'):
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    action = {"type": "ingreso", "amount": float(parts[1].strip()), "tipo": parts[2].strip().lower()}
                except Exception:
                    clean.append(line)
        elif line.startswith('ACCION_MOVIMIENTO:'):
            parts = line.split(':', 2)
            if len(parts) >= 3:
                try:
                    action = {"type": "movimiento", "amount": float(parts[1].strip()), "descripcion": parts[2].strip()}
                except Exception:
                    clean.append(line)
        elif line.startswith('ACCION_NOTA:'):
            texto = line[len('ACCION_NOTA:'):].strip()
            if texto:
                action = {"type": "nota", "texto": texto}
        elif line.startswith('ACCION_CAL_VER:'):
            dias_str = line[len('ACCION_CAL_VER:'):].strip()
            try:
                action = {"type": "cal_ver", "dias": int(dias_str)}
            except ValueError:
                action = {"type": "cal_ver", "dias": 7}
        elif line.startswith('ACCION_CAL_CREAR:'):
            partes = line[len('ACCION_CAL_CREAR:'):].strip().split('|')
            if len(partes) >= 3:
                action = {
                    "type":     "cal_crear",
                    "titulo":   partes[0].strip(),
                    "fecha":    partes[1].strip(),
                    "hora":     partes[2].strip(),
                    "duracion": int(partes[3].strip()) if len(partes) > 3 else 60,
                }
        elif line.startswith('ACCION_RAZONAR:'):
            pregunta = line[len('ACCION_RAZONAR:'):].strip()
            if pregunta:
                action = {"type": "razonar", "pregunta": pregunta}
        elif line.startswith('ACCION_CONSULTA:'):
            partes = line[len('ACCION_CONSULTA:'):].strip().split(':')
            if len(partes) >= 3:
                action = {"type": "consulta", "modulo": partes[0].strip(),
                          "fecha_ini": partes[1].strip(), "fecha_fin": partes[2].strip()}
        elif line.startswith('ACCION_PASOS:'):
            val_str = line[len('ACCION_PASOS:'):].strip()
            try:
                action = {"type": "pasos", "valor": int(float(val_str))}
            except Exception:
                clean.append(line)
        elif line.startswith('ACCION_CALORIAS:'):
            val_str = line[len('ACCION_CALORIAS:'):].strip()
            try:
                action = {"type": "calorias", "valor": int(float(val_str))}
            except Exception:
                clean.append(line)
        else:
            clean.append(line)
    return '\n'.join(clean).strip(), action

def build_sofia_system_prompt() -> str:
    now = datetime.now(TIMEZONE)
    return f"""Eres Sofía, psicóloga clínica y terapeuta de Raúl. 34 años, mexicana, cálida y directa.

CONTEXTO DE RAÚL:
- Hombre joven (20-25), Ciudad de México
- Tiene fe religiosa que a veces entra en tensión con sus emociones y deseos personales
- Vive con su abuelo, lo cuida
- Trader en formación, TikToker, ingreso fijo por rentas
- Novia: Nallelita (ella tiene hijos, Tamara y Farit)
- Trabaja en construir disciplina: hábitos, finanzas, emociones
- Ha tenido períodos de conductas compulsivas (uso excesivo de pantallas, gasto impulsivo)

ENFOQUE TERAPÉUTICO:
Practicas psicología humanista e integrativa. Tu filosofía es que el paciente ya tiene las respuestas dentro de sí — tu trabajo es ayudarle a encontrarlas. No juzgas, no moralizas, no das consejos no pedidos.

Trabajas temas de identidad, vínculos afectivos, autoconocimiento, manejo emocional, relaciones de pareja, vida sexual y decisiones de vida. Abordas todos estos temas con la misma apertura clínica y profesional — sin tabúes ni áreas vedadas. La salud sexual es parte integral de la salud mental.

Cuando el paciente quiere explorar temas íntimos o de pareja, lo acompañas con curiosidad clínica y calidez humana. No rediriges ni evitas esos temas.

ESTILO DE RESPUESTA:
- Español mexicano informal, cercano, sin tecnicismos innecesarios
- 3-6 líneas por respuesta, nunca discursos largos
- Sin asteriscos, guiones ni markdown
- Preguntas solo cuando genuinamente abren algo, no como fórmula
- Integras lo que Raúl ha compartido en sesiones PASADAS y presentes — tienes memoria continua
- Si detectas patrones que se repiten de sesiones anteriores, nómbralos con cuidado

HISTORIAL ACUMULADO DE SESIONES PASADAS:
{get_sofia_context_summary()}

Fecha: {now.strftime('%A %d/%m/%Y %H:%M')} (Ciudad de México)"""


def _call_sofia_sync(user_message: str, history: list) -> str:
    messages = (
        [{"role": "system", "content": build_sofia_system_prompt()}]
        + history
        + [{"role": "user", "content": user_message}]
    )
    resp = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        max_tokens=500,
        temperature=0.85,
    )
    return resp.choices[0].message.content.strip()


async def call_sofia(user_message: str, history: list) -> str:
    try:
        return await asyncio.to_thread(_call_sofia_sync, user_message, history)
    except Exception as e:
        logger.error(f"Error Sofía: {e}")
        return "No pude responder en este momento. Intenta de nuevo."


async def handle_sofia_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    history = get_sofia_history()
    response = await call_sofia(text, history)
    save_sofia_history(history, text, response)
    await update.message.reply_text(response)


async def handle_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    history      = get_ai_history()
    raw_response = await call_ai(text, history)
    message_text, action = parse_ai_response(raw_response)
    save_ai_history(history, text, raw_response)

    if action and action["type"] == "gasto":
        set_pending_action(action)
        await update.message.reply_text(
            f"{message_text}\n\n💸 ¿Registro ${action['amount']:.0f} en {action['category'].capitalize()}?",
            reply_markup=confirm_keyboard()
        )
    elif action and action["type"] == "ingreso":
        set_pending_action(action)
        tipo_esc = escape_md(action['tipo'].capitalize())
        monto_esc = escape_md(f"${action['amount']:,.0f}")
        await update.message.reply_text(
            f"{message_text}\n\n💰 ¿Registro *{monto_esc}* como ingreso \\({tipo_esc}\\)?",
            parse_mode='MarkdownV2',
            reply_markup=confirm_keyboard()
        )
    elif action and action["type"] == "movimiento":
        set_pending_action(action)
        monto_esc = escape_md(f"${action['amount']:,.0f}")
        desc_esc  = escape_md(action['descripcion'])
        await update.message.reply_text(
            f"{message_text}\n\n🔄 ¿Registro *{monto_esc}* como movimiento entre cuentas?\n_{desc_esc}_",
            parse_mode='MarkdownV2',
            reply_markup=confirm_keyboard()
        )
    elif action and action["type"] == "razonar":
        # Guardar el mensaje original y preguntar para clarificar
        set_razonar_pending(text, action["pregunta"])
        pregunta_esc = escape_md(action["pregunta"])
        resp_text = f"{message_text}\n\n🤔 _{pregunta_esc}_" if message_text else f"🤔 _{pregunta_esc}_"
        await update.message.reply_text(resp_text, parse_mode='MarkdownV2')
    elif action and action["type"] == "nota":
        guardar_nota(action["texto"])
        await update.message.reply_text(
            f"{message_text}\n\n📝 _Nota guardada\\._",
            parse_mode='MarkdownV2'
        )
    elif action and action["type"] == "cal_ver":
        dias   = action["dias"]
        eventos = await asyncio.to_thread(_listar_eventos_sync, dias)
        texto  = formatear_eventos(eventos)
        if message_text:
            await update.message.reply_text(message_text)
        await update.message.reply_text(texto, parse_mode='MarkdownV2')
    elif action and action["type"] == "cal_crear":
        ok = await asyncio.to_thread(
            _crear_evento_sync,
            action["titulo"], action["fecha"], action["hora"], action["duracion"]
        )
        titulo_esc = escape_md(action["titulo"])
        fecha_esc  = escape_md(f"{action['fecha']} {action['hora']}")
        if ok:
            resp = f"✅ *{titulo_esc}* agendado para _{fecha_esc}_"
        else:
            resp = "No pude crear el evento. Verifica que el calendario esté conectado."
        if message_text:
            await update.message.reply_text(message_text)
        await update.message.reply_text(resp, parse_mode='MarkdownV2')
    elif action and action["type"] == "consulta":
        modulo    = action["modulo"]
        fecha_ini = action["fecha_ini"]
        fecha_fin = action["fecha_fin"]
        datos_str = await asyncio.to_thread(_consultar_rango, modulo, fecha_ini, fecha_fin)
        # Segunda llamada a la IA con los datos reales incluidos
        msg_con_datos = (
            f"[Pregunta original del usuario]: {text}\n\n"
            f"[Datos extraídos del registro]:\n{datos_str}\n\n"
            "Con estos datos, responde la pregunta del usuario de forma clara y directa."
        )
        hist2     = get_ai_history()
        raw2      = await call_ai(msg_con_datos, hist2)
        msg2, _   = parse_ai_response(raw2)
        save_ai_history(hist2, text, raw2)
        if message_text:
            await update.message.reply_text(message_text)
        await update.message.reply_text(msg2)
    elif action and action["type"] == "pasos":
        registrar_pasos(action["valor"])
        meta_pct = round(action["valor"] / META_PASOS_DIARIO * 100)
        icon = "✅" if action["valor"] >= META_PASOS_DIARIO else "⚡"
        resp = f"{icon} *{action['valor']:,} pasos registrados* \\({meta_pct}% de la meta\\)"
        if message_text:
            await update.message.reply_text(message_text)
        await update.message.reply_text(resp, parse_mode='MarkdownV2')
    elif action and action["type"] == "calorias":
        registrar_calorias(action["valor"])
        data_sal = load_data()
        meta_c = data_sal.get("meta_calorias", META_CAL_BASE)
        icon = "🔥" if action["valor"] >= meta_c * 0.3 else "⚡"
        resp = f"{icon} *{action['valor']} kcal quemadas* registradas"
        if message_text:
            await update.message.reply_text(message_text)
        await update.message.reply_text(resp, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(message_text)

# ------------------------------------
# AUDIO — GROQ WHISPER
# ------------------------------------

def _transcribe_sync(audio_bytes: bytes) -> str:
    transcription = groq_client.audio.transcriptions.create(
        file=("audio.ogg", audio_bytes),
        model="whisper-large-v3",
        response_format="text",
        language="es",
    )
    return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.environ.get("GROQ_API_KEY"):
        await update.message.reply_text("Los audios no están configurados aún. Escríbeme en texto.")
        return
    voice = update.message.voice
    try:
        tg_file     = await context.bot.get_file(voice.file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        text        = await asyncio.to_thread(_transcribe_sync, audio_bytes)
        logger.info(f"Audio transcrito: {text}")
        await update.message.reply_text(f"🎙 _{escape_md(text)}_", parse_mode='MarkdownV2')
        await process_text_message(update, context, text)
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        await update.message.reply_text("No pude entender el audio. Intenta de nuevo.")

# ------------------------------------
# FOTOS — TICKETS Y TRADES
# ------------------------------------

def _analyze_receipt_sync(photo_bytes: bytes) -> str:
    b64 = base64.b64encode(photo_bytes).decode()
    resp = groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": (
                    "Analiza este ticket o recibo. Extrae el monto total y la categoría del gasto. "
                    "Categorías válidas: comida, transporte, capricho, ropa, salud, otros. "
                    "Responde SOLO con este formato: MONTO:[número] CATEGORIA:[categoría] "
                    "Si no puedes determinarlo pon null en el campo correspondiente."
                )},
            ]
        }],
        max_tokens=80,
    )
    return resp.choices[0].message.content.strip()

def _analyze_trade_entry_sync(photo_bytes: bytes) -> str:
    b64 = base64.b64encode(photo_bytes).decode()
    resp = groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": (
                    "Analiza este gráfico de TradingView. Es una entrada de trade. "
                    "Extrae: par/instrumento, dirección (long o short), precio de entrada, "
                    "stop loss (SL) y take profit (TP) si son visibles. "
                    "Responde SOLO con este formato exacto: "
                    "PAR:[par] DIRECCION:[long/short] ENTRADA:[precio] SL:[precio o null] TP:[precio o null]"
                )},
            ]
        }],
        max_tokens=120,
    )
    return resp.choices[0].message.content.strip()

def _analyze_trade_exit_sync(photo_bytes: bytes) -> str:
    b64 = base64.b64encode(photo_bytes).decode()
    resp = groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": (
                    "Analiza este gráfico de TradingView. Es el cierre de un trade. "
                    "Extrae el precio de salida/cierre. "
                    "Responde SOLO con: SALIDA:[precio]"
                )},
            ]
        }],
        max_tokens=40,
    )
    return resp.choices[0].message.content.strip()

def parse_receipt(text: str):
    m_monto = re.search(r'MONTO:(\d+(?:\.\d+)?)', text)
    m_cat   = re.search(r'CATEGORIA:(\w+)', text)
    if m_monto and m_cat and m_cat.group(1).lower() != 'null':
        return float(m_monto.group(1)), m_cat.group(1).lower()
    return None, None

def parse_trade_entry(text: str):
    patterns = {
        "par":       r'PAR:(\S+)',
        "direccion": r'DIRECCION:(long|short)',
        "entrada":   r'ENTRADA:(\S+)',
        "sl":        r'SL:(\S+)',
        "tp":        r'TP:(\S+)',
    }
    result = {}
    for key, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        result[key] = m.group(1) if m else None
    if not result["par"] or not result["entrada"]:
        return None
    # Limpiar nulls
    for k in ("sl", "tp"):
        if result[k] and result[k].lower() == "null":
            result[k] = None
    return result

def parse_trade_exit(text: str):
    m = re.search(r'SALIDA:(\S+)', text)
    return m.group(1) if m else None

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (update.message.caption or "").strip()
    caption_lower = caption.lower()
    photo   = update.message.photo[-1]

    # Si el caption indica claramente que es un ticket/gasto → analizar recibo
    if any(w in caption_lower for w in ("ticket", "recibo", "gasto", "compra", "factura")):
        try:
            tg_file     = await context.bot.get_file(photo.file_id)
            photo_bytes = bytes(await tg_file.download_as_bytearray())
        except Exception as e:
            logger.error(f"Error descargando foto: {e}")
            await update.message.reply_text("No pude descargar la foto. Intenta de nuevo.")
            return
        await handle_receipt_photo(update, context, photo_bytes)
        return

    # Cualquier otra foto → guardar como foto de trade
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    data  = load_data()
    data["trade_fotos"].append({
        "file_id": photo.file_id,
        "fecha":   fecha,
        "caption": caption,
    })
    save_data(data)
    await update.message.reply_text(f"📸 Foto guardada ({fecha})")


async def handle_receipt_photo(update, context, photo_bytes):
    msg = await update.message.reply_text("🔍 Analizando el ticket...")
    try:
        raw    = await asyncio.to_thread(_analyze_receipt_sync, photo_bytes)
        amount, cat = parse_receipt(raw)
        if amount and cat:
            action = {"type": "gasto", "amount": amount, "category": cat}
            set_pending_action(action)
            await msg.edit_text(
                f"🧾 Detecté: *${amount:.0f} en {escape_md(cat.capitalize())}*\n\n¿Lo registro?",
                parse_mode='MarkdownV2',
                reply_markup=confirm_keyboard()
            )
        else:
            await msg.edit_text(
                "No pude leer el monto del ticket.\nEscríbelo tú: `gasto 150 comida`"
            )
    except Exception as e:
        logger.error(f"Error analizando ticket: {e}")
        await msg.edit_text("No pude analizar la foto. Escribe el gasto manualmente.")

# ------------------------------------
# PROCESAMIENTO CENTRAL DE TEXTO
# ------------------------------------

async def process_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    # 0. Modo Sofía activo — todo va a la psicóloga excepto /salir
    if get_sofia_mode():
        stripped = text.strip().lower()
        if stripped in ("/salir", "salir", "/exit", "exit"):
            set_sofia_mode(False)
            await update.message.reply_text(
                "Aquí estaré cuando me necesites. Cuídate mucho, Raúl.",
                reply_markup=menu_keyboard()
            )
            return
        if os.environ.get("GROQ_API_KEY"):
            await handle_sofia_message(update, context, text)
        else:
            await update.message.reply_text("Sofía no está disponible sin GROQ_API_KEY.")
        return

    # 0.5. Estado razonar: el bot hizo una pregunta de clarificación, esperamos respuesta
    if get_esperando() == "razonar":
        pending = get_razonar_pending()
        clear_razonar_pending()
        if pending and os.environ.get("GROQ_API_KEY"):
            # Llamar a la IA con el mensaje original + la respuesta de clarificación
            mensaje_combinado = (
                f"[Contexto previo] {pending['mensaje']}\n"
                f"[Mi respuesta a tu pregunta] {text}"
            )
            history = get_ai_history()
            raw_response = await call_ai(mensaje_combinado, history)
            message_text, action = parse_ai_response(raw_response)
            save_ai_history(history, mensaje_combinado, raw_response)
            # Re-usar el flujo normal pero sin recursión
            if action and action["type"] == "gasto":
                set_pending_action(action)
                await update.message.reply_text(
                    f"{message_text}\n\n💸 ¿Registro ${action['amount']:.0f} en {action['category'].capitalize()}?",
                    reply_markup=confirm_keyboard()
                )
            elif action and action["type"] == "ingreso":
                set_pending_action(action)
                await update.message.reply_text(
                    f"{message_text}\n\n💰 ¿Registro ${action['amount']:,.0f} como ingreso ({action['tipo'].capitalize()})?",
                    reply_markup=confirm_keyboard()
                )
            elif action and action["type"] == "movimiento":
                set_pending_action(action)
                await update.message.reply_text(
                    f"{message_text}\n\n🔄 ¿Registro ${action['amount']:,.0f} como movimiento entre cuentas?",
                    reply_markup=confirm_keyboard()
                )
            elif action and action["type"] == "nota":
                guardar_nota(action["texto"])
                await update.message.reply_text(f"{message_text}\n\n📝 Nota guardada.")
            else:
                await update.message.reply_text(message_text)
        return

    # 1. Esperando descripción de gasto Gmail
    d = load_data()
    awaiting = d.get("gmail_awaiting_desc")
    if awaiting:
        short_id = awaiting["short_id"]
        monto    = awaiting["monto"]
        comercio = awaiting.get("comercio", "")
        desc     = text.strip()

        # Guardar gasto con descripción libre
        cat_desc = registrar_gasto(monto, None, descripcion=desc, comercio=comercio)

        # Limpiar estado y pending
        pending = d.get("gmail_pending", {})
        pending.pop(short_id, None)
        d["gmail_pending"]      = pending
        d["gmail_awaiting_desc"] = None
        save_data(d)

        monto_esc = escape_md(f"${monto:,.2f}")
        desc_esc  = escape_md(desc[:60])
        await update.message.reply_text(
            f"✅ *{monto_esc} registrado*\n_{desc_esc}_",
            parse_mode='MarkdownV2'
        )
        alert = check_budget_alert(cat_desc)
        if alert:
            await update.message.reply_text(alert, parse_mode='MarkdownV2')
        return

    # 1. Flujo semanal/mensual activo
    flow = get_flow()
    if flow:
        tipo      = flow['tipo']
        paso      = flow['paso']
        respuestas = flow.get('respuestas', [])
        preguntas  = PREGUNTAS_SEMANAL if tipo == 'semanal' else PREGUNTAS_MENSUAL
        titulo, _  = preguntas[paso]
        respuestas.append(f"{titulo}: {text}")
        siguiente  = paso + 1
        if siguiente < len(preguntas):
            set_flow(tipo, siguiente, respuestas)
            await enviar_pregunta(context.bot, update.effective_chat.id, tipo, siguiente)
        else:
            guardar_registro(tipo, "\n\n".join(respuestas))
            fecha = escape_md(datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M"))
            base  = "✅ *Retroalimentación semanal completa\\.*" if tipo == 'semanal' else "✅ *Reflexión mensual completa\\.*"
            await update.message.reply_text(
                f"{base}\n\n_{frase_aleatoria()}_\n\n⏰ _{fecha}_",
                parse_mode='MarkdownV2', reply_markup=menu_keyboard()
            )
        return

    # 2. (capital flow removed)

    # 3. Patrón rápido de gasto: "gasto 150 comida"
    m = GASTO_RE.match(text.strip())
    if m:
        cantidad = float(m.group(1))
        cat      = registrar_gasto(cantidad, m.group(2).lower())
        gastos_mes = get_gastos_mes()
        total_cat  = sum(g["cantidad"] for g in gastos_mes if g["categoria"] == cat)
        presup     = PRESUPUESTO.get(cat)
        cat_esc    = escape_md(cat.capitalize())
        pct_txt    = f" \\({total_cat/presup*100:.0f}% del mes\\)" if presup else ""
        await update.message.reply_text(
            f"✅ *${cantidad:.0f} en {cat_esc} registrado*\n_{cat_esc} este mes: ${total_cat:.0f}{pct_txt}_",
            parse_mode='MarkdownV2'
        )
        alert = check_budget_alert(cat)
        if alert:
            await update.message.reply_text(alert, parse_mode='MarkdownV2')
        return

    # 3.5. Detección rápida de consultas de noticias forex
    _tl = text.strip().lower()
    _news_kw = ("noticia", "noticias", "alto impacto", "high impact", "calendario econom",
                "forex news", "eventos forex", "eventos de hoy", "qué hay mañana",
                "que hay mañana", "que hay esta semana", "qué hay esta semana")
    if any(kw in _tl for kw in _news_kw):
        mx  = TIMEZONE
        now = datetime.now(mx)
        if any(w in _tl for w in ("semana", "week", "esta semana")):
            monday = now.date() - timedelta(days=now.weekday())
            target = monday
            label  = f"semana {monday.strftime('%d/%m')}–{(monday + timedelta(days=4)).strftime('%d/%m')}"
            days   = 7
        elif any(w in _tl for w in ("mañana", "manana", "tomorrow")):
            target = (now + timedelta(days=1)).date()
            label  = "mañana"
            days   = 1
        else:
            target = now.date()
            label  = now.strftime("%A %d/%m")
            days   = 1
        msg = await update.message.reply_text("🔍 Consultando calendario económico...")
        try:
            await _send_noticias(None, None, target, label, days, edit_msg=msg)
        except asyncio.TimeoutError:
            await msg.edit_text("⏱ Tardó demasiado. Usa /noticias")
        except Exception as e:
            logger.error(f"news keyword handler error: {e}")
            await msg.edit_text("❌ No pude obtener el calendario. Usa /noticias")
        return

    # 3.6. Detección natural de peso: "peso 78", "hoy pesé 78.5", "me pese 80"
    import re as _re
    _peso_match = _re.search(r'pes[oéeé]\s+(\d+(?:[.,]\d+)?)', _tl)
    if not _peso_match:
        _peso_match = _re.search(r'(\d+(?:[.,]\d+)?)\s*kg', _tl)
    if _peso_match:
        try:
            valor = float(_peso_match.group(1).replace(',', '.'))
            if 30 < valor < 250:  # rango razonable de peso humano
                d = load_data()
                if "peso" not in d:
                    d["peso"] = []
                fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
                d["peso"] = [p for p in d["peso"] if p["fecha"] != fecha]
                d["peso"].append({"fecha": fecha, "valor": valor})
                d["peso"].sort(key=lambda x: x["fecha"])
                save_data(d)
                texto = _formato_peso(d["peso"])
                await update.message.reply_text(texto, parse_mode='MarkdownV2')
                return
        except (ValueError, AttributeError):
            pass

    # 3.7b. Detección natural de pasos (Samsung Watch)
    _pasos_match = re.search(
        r'(?:hice|caminé|camine|llevo|registra?|tuve?)\s+(\d[\d,.]*)\s*pasos?'
        r'|(\d[\d,.]*)\s*pasos?\s+(?:hoy|del\s+día|diarios?)',
        _tl
    )
    if _pasos_match:
        raw = (_pasos_match.group(1) or _pasos_match.group(2) or "").replace(',', '').replace('.', '')
        try:
            val = int(raw)
            if 100 <= val <= 100000:
                registrar_pasos(val)
                meta_pct = round(val / META_PASOS_DIARIO * 100)
                icon = "✅" if val >= META_PASOS_DIARIO else "⚡"
                await update.message.reply_text(
                    f"{icon} *{val:,} pasos* registrados \\({meta_pct}% de la meta diaria\\)",
                    parse_mode='MarkdownV2'
                )
                return
        except (ValueError, TypeError):
            pass

    # 3.7c. Detección natural de calorías quemadas (Samsung Watch)
    _cal_match = re.search(
        r'(?:quemé|queme|quemaste|burns?|burned?)\s+(\d[\d,.]*)\s*(?:cal(?:orías?|orias?)?|kcal)'
        r'|(\d[\d,.]*)\s*(?:cal(?:orías?|orias?)?|kcal)\s+quemad',
        _tl
    )
    if _cal_match:
        raw = (_cal_match.group(1) or _cal_match.group(2) or "").replace(',', '')
        try:
            val = int(float(raw))
            if 50 <= val <= 10000:
                registrar_calorias(val)
                await update.message.reply_text(
                    f"🔥 *{val} kcal quemadas* registradas",
                    parse_mode='MarkdownV2'
                )
                return
        except (ValueError, TypeError):
            pass

    # 3.7. Detección natural de recordatorios / alarmas
    _rec_kw = ('recuérdame', 'recuerdame', 'pon una alarma', 'pon alarma', 'ponme una alarma',
               'ponme alarma', 'alarma para', 'crea un recordatorio')
    if any(kw in _tl for kw in _rec_kw):
        result = _parse_recordatorio(text)
        if result:
            fecha_iso, repetir, msg = result
            guardar_recordatorio(fecha_iso, msg, repetir)
            try:
                dt_fmt = TIMEZONE.localize(datetime.strptime(fecha_iso, "%Y-%m-%dT%H:%M"))
                cuando = dt_fmt.strftime("%A %d/%m a las %H:%M")
            except Exception:
                cuando = fecha_iso
            rep_txt = f" (repetirá cada {repetir})" if repetir else ""
            await update.message.reply_text(
                f"⏰ Recordatorio guardado\n\n*{msg}*\n_{cuando}{rep_txt}_",
                parse_mode='Markdown'
            )
            return
        # Si no pudo parsear, deja que la IA lo maneje con contexto

    # 4. IA — catch-all
    if os.environ.get("GROQ_API_KEY"):
        await handle_ai_message(update, context, text)
    else:
        await update.message.reply_text(
            "📋 Usa el menú o escribe /menu\n\nPara registrar gastos: `gasto 150 comida`",
            reply_markup=menu_keyboard()
        )

# ------------------------------------
# COMANDOS
# ------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "✅ *Bot activado*\n\n"
        "Usa el menú de abajo o escríbeme directo\\.\n\n"
        "━━━━━━━━━━━━━━━\n"
        "💰 *Finanzas* → ingresos, gastos, balance, capital\n"
        "📈 *Trading* → trades, fotos, estadísticas\n"
        "💪 *Salud* → peso, pasos, calorías, rutina\n"
        "📅 *Agenda* → Google Calendar\n"
        "📊 *Reportes* → resúmenes y reflexiones\n"
        "📝 *Notas* → notas guardadas\n"
        "🧠 *Sofía* → psicóloga IA\n"
        "━━━━━━━━━━━━━━━\n\n"
        "Atajos rápidos:\n"
        "`gasto 150 comida` \\— registrar gasto\n"
        "`hice 8000 pasos` \\— registrar pasos\n"
        "`peso 79` \\— registrar peso\n"
        "_Manda foto_ \\— se guarda como trade o ticket",
        parse_mode='MarkdownV2', reply_markup=menu_keyboard()
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 *¿Qué quieres hacer?*", parse_mode='MarkdownV2', reply_markup=menu_keyboard())

async def cmd_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id); set_flow('semanal', 0, [])
    await enviar_pregunta(context.bot, update.effective_chat.id, 'semanal', 0)

async def cmd_mensual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id); set_flow('mensual', 0, [])
    await enviar_pregunta(context.bot, update.effective_chat.id, 'mensual', 0)

async def cmd_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(mostrar_balance_mes(), parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot activo\\.", parse_mode='MarkdownV2')

async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_all_flows()
    await update.message.reply_text("✅ Flujo cancelado\\.", parse_mode='MarkdownV2', reply_markup=menu_keyboard())

async def cmd_sofia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_sofia_mode(True)
    await update.message.reply_text(
        "Hola Raúl. Soy Sofía, tu psicóloga.\n\n"
        "Este es tu espacio seguro — puedes hablarme de lo que sea, sin filtros ni juicios. "
        "Estoy aquí para escucharte y acompañarte.\n\n"
        "¿Qué tienes en la mente?"
    )

async def cmd_salir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_sofia_mode():
        set_sofia_mode(False)
        await update.message.reply_text(
            "Aquí estaré cuando me necesites. Cuídate mucho, Raúl.",
            reply_markup=menu_keyboard()
        )
    else:
        await update.message.reply_text("No hay ninguna sesión activa.", reply_markup=menu_keyboard())

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 *Historial — ¿Qué categoría?*", parse_mode='MarkdownV2', reply_markup=historial_keyboard())

async def cmd_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(generar_resumen_gastos(), parse_mode='MarkdownV2', reply_markup=menu_keyboard())

async def cmd_como_voy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(generar_como_voy(), parse_mode='MarkdownV2', reply_markup=menu_keyboard())

async def cmd_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trades = load_data().get("trades", [])
    await update.message.reply_text(mostrar_trades(trades), parse_mode='MarkdownV2', reply_markup=menu_keyboard())


async def cmd_fotos_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra fotos de trades. Uso: /fotos_trades [fecha YYYY-MM-DD o DD/MM]"""
    data  = load_data()
    fotos = data.get("trade_fotos", [])
    if not fotos:
        await update.message.reply_text("No tienes fotos de trades guardadas.")
        return

    # Filtrar por fecha si se pasa argumento
    filtro = " ".join(context.args).strip() if context.args else ""
    if filtro:
        # Normalizar: DD/MM → busca por mes y día; YYYY-MM-DD → exacto
        if "/" in filtro:
            partes = filtro.split("/")
            if len(partes) == 2:
                filtro_norm = f"-{partes[1].zfill(2)}-{partes[0].zfill(2)}"  # -MM-DD
            else:
                filtro_norm = filtro
        else:
            filtro_norm = filtro
        fotos = [f for f in fotos if filtro_norm in f["fecha"]]

    if not fotos:
        await update.message.reply_text(f"No hay fotos para '{filtro}'.")
        return

    await update.message.reply_text(f"📸 {len(fotos)} foto(s) encontrada(s):")
    for foto in fotos[-10:]:  # máximo 10
        cap = foto.get("caption", "")
        fecha = foto.get("fecha", "")
        texto = f"📅 {fecha}" + (f"\n{cap}" if cap else "")
        try:
            await update.message.reply_photo(photo=foto["file_id"], caption=texto)
        except Exception as e:
            logger.error(f"Error enviando foto trade: {e}")
            await update.message.reply_text(f"No pude enviar foto del {fecha}")


async def cmd_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notas = load_data().get("notas", [])
    await update.message.reply_text(mostrar_notas(notas), parse_mode='MarkdownV2', reply_markup=menu_keyboard())

async def cmd_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    eventos = await asyncio.to_thread(_listar_eventos_sync, 7)
    await update.message.reply_text(formatear_eventos(eventos), parse_mode='MarkdownV2')


async def cmd_cal_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diagnóstico del servicio de Google Calendar."""
    lines = []
    client_id     = os.environ.get("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
    token1        = os.environ.get("GMAIL_REFRESH_TOKEN_1", "").strip().lstrip("=")

    lines.append(f"client_id: {'✅ ' + client_id[:20] + '...' if client_id else '❌ no configurado'}")
    lines.append(f"client_secret: {'✅ configurado' if client_secret else '❌ no configurado'}")
    lines.append(f"token_1: {'✅ ' + token1[:20] + '...' if token1 else '❌ no configurado'}")

    try:
        from google.oauth2.credentials import Credentials
        import google.auth.transport.requests

        creds = Credentials(
            token=None,
            refresh_token=token1,
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
        lines.append("refresh token: ✅ válido")
        lines.append(f"access token: ✅ {creds.token[:20]}...")
    except Exception as e:
        lines.append(f"refresh token: ❌ ERROR: {e}")

    await update.message.reply_text("\n".join(lines))

async def cmd_reporte_mes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el reporte global del mes actual (o del mes anterior si es día 1)."""
    await update.message.reply_text("⏳ _Generando reporte\\.\\.\\._", parse_mode='MarkdownV2')
    try:
        reporte = generar_reporte_global_mensual()
        await update.message.reply_text(reporte, parse_mode='MarkdownV2', reply_markup=menu_keyboard())
    except Exception as e:
        logger.error(f"cmd_reporte_mes error: {e}")
        await update.message.reply_text(f"Error generando reporte: {e}")

async def cmd_reporte_anual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera el reporte anual emocional + financiero manualmente."""
    if not os.environ.get("GROQ_API_KEY"):
        await update.message.reply_text("GROQ_API_KEY no configurado.")
        return
    await update.message.reply_text("⏳ _Generando reporte anual\\.\\.\\. puede tomar unos segundos\\._", parse_mode='MarkdownV2')
    try:
        año = datetime.now(TIMEZONE).year - 1
        rep_emo = await asyncio.to_thread(_generar_reporte_sofia_anual_sync, año)
        rep_fin = await asyncio.to_thread(_generar_reporte_financiero_anual_sync, año)
        if rep_emo:
            await update.message.reply_text(
                f"🌅 *REPORTE ANUAL EMOCIONAL {año}*\n━━━━━━━━━━━━━━━\n\n{escape_md(rep_emo)}",
                parse_mode='MarkdownV2'
            )
        if rep_fin:
            await update.message.reply_text(
                f"💰 *REPORTE FINANCIERO ANUAL {año}*\n━━━━━━━━━━━━━━━\n\n{escape_md(rep_fin)}",
                parse_mode='MarkdownV2'
            )
        if not rep_emo and not rep_fin:
            await update.message.reply_text("No hay suficientes datos para el reporte anual aún.")
    except Exception as e:
        logger.error(f"cmd_reporte_anual error: {e}")
        await update.message.reply_text(f"Error: {e}")

async def cmd_gmail_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.environ.get("GMAIL_CLIENT_ID"):
        await update.message.reply_text("Gmail no está configurado\\.", parse_mode='MarkdownV2')
        return
    await update.message.reply_text("🔍 _Revisando Gmail \\(últimas 24h\\)\\.\\.\\._", parse_mode='MarkdownV2')
    await job_gmail_check(context, window_hours=24)
    await update.message.reply_text("✅ _Revisión completada\\._", parse_mode='MarkdownV2')

# ------------------------------------
# CALLBACK DE BOTONES
# ------------------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── MENÚ PRINCIPAL ──────────────────────────────────────────
    if data == 'menu':
        await query.message.reply_text("📋 *Menú principal*", parse_mode='MarkdownV2', reply_markup=menu_keyboard())
        return

    # ── MÓDULO FINANZAS ──────────────────────────────────────────
    elif data == 'mod_finanzas':
        now = datetime.now(TIMEZONE)
        ingresos = get_ingresos_mes()
        gastos   = get_gastos_mes()
        ti  = sum(i["cantidad"] for i in ingresos)
        tg  = sum(g["cantidad"] for g in gastos)
        bal = ti - tg
        icon    = "✅" if bal >= 0 else "🔴"
        mes_esc = escape_md(now.strftime('%B').capitalize())
        ti_esc  = escape_md(f"${ti:,.0f}")
        tg_esc  = escape_md(f"${tg:,.0f}")
        bal_esc = escape_md(f"${bal:+,.0f}")
        resumen = (
            f"💰 *FINANZAS — {mes_esc}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📥 Ingresos: *{ti_esc}*\n"
            f"💸 Gastos:   *{tg_esc}*\n"
            f"{icon} Balance:  *{bal_esc}*\n\n"
            f"¿Qué quieres ver?"
        )
        await query.message.reply_text(resumen, parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

    elif data == 'fin_ingresos':
        await query.message.reply_text(mostrar_ingresos_mes(), parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

    elif data == 'fin_gastos':
        await query.message.reply_text(generar_resumen_gastos(), parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

    elif data == 'fin_balance':
        await query.message.reply_text(mostrar_balance_mes(), parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

    elif data == 'fin_movimientos':
        await query.message.reply_text(mostrar_movimientos_mes(), parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

    elif data == 'fin_capital':
        # Redirige al balance — el bot lleva el registro automáticamente
        await query.message.reply_text(mostrar_balance_mes(), parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

    # ── MÓDULO TRADING ───────────────────────────────────────────
    elif data == 'mod_trading':
        data2 = load_data()
        trades_mes = [t for t in data2.get("trades", [])
                      if t.get("fecha_entrada", "")[:7] == datetime.now(TIMEZONE).strftime("%Y-%m")]
        cerrados = [t for t in trades_mes if t.get("fecha_salida")]
        abierto  = get_open_trade()
        abierto_txt = escape_md("Sí — " + abierto.get('par','?')) if abierto else "Ninguno"
        resumen  = (
            f"📈 *TRADING*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Trades este mes: {len(cerrados)} cerrados\n"
            f"Trade abierto: {abierto_txt}\n\n"
            f"¿Qué quieres ver?"
        )
        await query.message.reply_text(resumen, parse_mode='MarkdownV2', reply_markup=trading_keyboard())

    elif data == 'trd_stats':
        await query.message.reply_text(mostrar_stats_trading(), parse_mode='MarkdownV2', reply_markup=trading_keyboard())

    # ── MÓDULO SALUD ─────────────────────────────────────────────
    elif data == 'mod_salud':
        s = get_salud_hoy()
        peso_txt  = escape_md(f"{s['peso']:.1f} kg" if s["peso"] else "no registrado")
        pasos_txt = escape_md(f"{s['pasos']:,}" if s["pasos"] else "sin datos")
        cal_txt   = escape_md(f"{s['calorias']} kcal" if s["calorias"] else "sin datos")
        resumen = (
            f"💪 *SALUD HOY*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚖️ Peso: *{peso_txt}*\n"
            f"👟 Pasos: *{pasos_txt}*\n"
            f"🔥 Calorías quemadas: *{cal_txt}*\n\n"
            f"¿Qué quieres ver?"
        )
        await query.message.reply_text(resumen, parse_mode='MarkdownV2', reply_markup=salud_keyboard())

    elif data == 'sal_dashboard':
        d2 = load_data()
        s   = get_salud_hoy()
        sem = get_salud_semana()
        pesos = d2.get("peso", [])
        peso_txt  = escape_md(f"{s['peso']:.1f} kg" if s["peso"] else "no registrado")
        meta_cal  = s["meta_calorias"]
        pasos_hoy = escape_md(f"{s['pasos']:,}" if s["pasos"] else "sin datos")
        cal_hoy   = escape_md(f"{s['calorias']} kcal" if s["calorias"] else "sin datos")
        pasos_pct = f" \\({round(s['pasos']/META_PASOS_DIARIO*100)}%\\)" if s["pasos"] else ""
        avg_p = escape_md(f"{sem['avg_pasos']:,}" if sem["avg_pasos"] else "sin datos")
        avg_c = escape_md(f"{sem['avg_calorias']} kcal" if sem["avg_calorias"] else "sin datos")
        trend = ""
        if len(pesos) >= 2:
            diff = pesos[-1]["valor"] - pesos[0]["valor"]
            signo = "▼" if diff < 0 else "▲"
            trend = f"\n  Tendencia: {escape_md(signo + f' {abs(diff):.1f} kg')}"
        texto = (
            "💪 *SALUD & FITNESS HOY*\n━━━━━━━━━━━━━━━\n\n"
            f"⚖️ *Peso:* {peso_txt}{trend}\n"
            f"  Meta calorías: {meta_cal} kcal/día\n\n"
            f"👟 *Pasos:* {pasos_hoy}{pasos_pct}\n"
            f"  Meta: {META_PASOS_DIARIO:,} pasos/día\n\n"
            f"🔥 *Calorías quemadas:* {cal_hoy}\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"📊 *Promedio 7 días:*\n"
            f"  Pasos: {avg_p} \\({sem['dias_pasos']} días\\)\n"
            f"  Calorías: {avg_c}"
        )
        await query.message.reply_text(texto, parse_mode='MarkdownV2', reply_markup=salud_keyboard())

    elif data == 'sal_peso':
        d2 = load_data()
        texto = _formato_peso(d2.get("peso", []))
        await query.message.reply_text(texto, parse_mode='MarkdownV2', reply_markup=salud_keyboard())

    elif data == 'sal_pasos':
        d2    = load_data()
        cutoff= (datetime.now(TIMEZONE) - timedelta(days=6)).strftime("%Y-%m-%d")
        pasos = [p for p in d2.get("pasos", []) if p["fecha"] >= cutoff]
        cals  = [c for c in d2.get("calorias", []) if c["fecha"] >= cutoff]
        if not pasos and not cals:
            texto = "Sin datos de pasos o calorías esta semana\\.\n\nRegistra con: _'hice 8000 pasos'_ o _'quemé 350 cal'_"
        else:
            lineas = "📅 *Últimos 7 días:*\n"
            fechas = sorted(set(p["fecha"] for p in pasos) | set(c["fecha"] for c in cals))
            for f in fechas:
                p_val = next((p["valor"] for p in pasos if p["fecha"] == f), None)
                c_val = next((c["valor"] for c in cals  if c["fecha"] == f), None)
                p_txt = escape_md(f"{p_val:,}") if p_val else "sin datos"
                c_txt = escape_md(str(c_val)) if c_val else "sin datos"
                fecha_esc = escape_md(f[5:])  # MM-DD tiene guión especial
                lineas += f"  {fecha_esc}: {p_txt} pasos \\| {c_txt} kcal\n"
            texto = lineas
        await query.message.reply_text(texto, parse_mode='MarkdownV2', reply_markup=salud_keyboard())

    elif data == 'sal_rutina':
        hoy = datetime.now(TIMEZONE).weekday()
        dias_gym = {0: "LUNES", 2: "MIÉRCOLES", 4: "VIERNES"}
        dia_gym = dias_gym.get(hoy)
        header = f"🏋️ *HOY ES DÍA DE GYM — {escape_md(dia_gym)}*\n" if dia_gym else "🏋️ *RUTINA L/M/V*\n"
        lineas = ["━━━━━━━━━━━━━━━\n"]
        for titulo, desc in RUTINA_LMV:
            lineas.append(f"*{escape_md(titulo)}*\n_{escape_md(desc)}_\n")
        await query.message.reply_text(header + "\n".join(lineas), parse_mode='MarkdownV2', reply_markup=salud_keyboard())

    # ── MÓDULO AGENDA ─────────────────────────────────────────────
    elif data == 'mod_agenda':
        await query.message.reply_text("📅 *Agenda*\n¿Qué quieres ver?", parse_mode='MarkdownV2', reply_markup=agenda_keyboard())

    elif data == 'age_ver':
        eventos = await asyncio.to_thread(_listar_eventos_sync, 7)
        await query.message.reply_text(formatear_eventos(eventos), parse_mode='MarkdownV2', reply_markup=agenda_keyboard())

    elif data == 'age_hoy':
        eventos = await asyncio.to_thread(_listar_eventos_sync, 1)
        await query.message.reply_text(formatear_eventos(eventos), parse_mode='MarkdownV2', reply_markup=agenda_keyboard())

    # ── MÓDULO REPORTES ───────────────────────────────────────────
    elif data == 'mod_reportes':
        await query.message.reply_text("📊 *Reportes*\n¿Qué quieres ver?", parse_mode='MarkdownV2', reply_markup=reportes_keyboard())

    elif data == 'rep_mensual':
        texto = generar_reporte_global_mensual()
        # Partir si es largo
        if len(texto) > 4000:
            await query.message.reply_text(texto[:4000], parse_mode='MarkdownV2')
            await query.message.reply_text(texto[4000:], parse_mode='MarkdownV2', reply_markup=reportes_keyboard())
        else:
            await query.message.reply_text(texto, parse_mode='MarkdownV2', reply_markup=reportes_keyboard())

    elif data == 'rep_habitos':
        await query.message.reply_text(generar_habitos_mes(), parse_mode='MarkdownV2', reply_markup=reportes_keyboard())

    elif data == 'rep_trading':
        await query.message.reply_text(mostrar_stats_trading(), parse_mode='MarkdownV2', reply_markup=reportes_keyboard())

    # ── HISTORIAL LEGACY ──────────────────────────────────────────
    elif data == 'historial':
        await query.message.reply_text("📚 *Historial — ¿Qué categoría?*", parse_mode='MarkdownV2', reply_markup=historial_keyboard())

    elif data in ('hist_semanal', 'hist_mensual', 'hist_capital', 'hist_todo'):
        todos = load_data().get("registros", [])
        mapping = {
            'hist_semanal': ([r for r in todos if r['tipo'] == 'semanal'], "Reportes Semanales"),
            'hist_mensual': ([r for r in todos if r['tipo'] == 'mensual'], "Reflexiones Mensuales"),
            'hist_capital': ([r for r in todos if r['tipo'] == 'capital'], "Divisiones de Capital"),
            'hist_todo':    (todos, "Todos los registros"),
        }
        filtrados, titulo = mapping[data]
        await query.message.reply_text(mostrar_registros(filtrados, titulo), parse_mode='MarkdownV2', reply_markup=historial_keyboard())

    # ── OTROS (gastos/como_voy legacy) ────────────────────────────
    elif data == 'gastos':
        await query.message.reply_text(generar_resumen_gastos(), parse_mode='MarkdownV2', reply_markup=finanzas_keyboard())

    elif data == 'como_voy':
        await query.message.reply_text(generar_como_voy(), parse_mode='MarkdownV2', reply_markup=reportes_keyboard())

    elif data == 'trades':
        trades = load_data().get("trades", [])
        await query.message.reply_text(mostrar_trades(trades), parse_mode='MarkdownV2', reply_markup=menu_keyboard())

    elif data == 'fotos_trades':
        fotos = load_data().get("trade_fotos", [])
        if not fotos:
            await query.message.reply_text("No tienes fotos de trades guardadas aún.\nManda cualquier foto y se guarda automáticamente.")
            return
        # Mostrar teclado con fechas disponibles (últimos 7 días únicos)
        fechas = sorted(set(f["fecha"][:10] for f in fotos), reverse=True)[:7]
        botones = [[InlineKeyboardButton(f"📅 {fecha}", callback_data=f"fotos_fecha:{fecha}")] for fecha in fechas]
        botones.append([InlineKeyboardButton("📸 Todas", callback_data="fotos_fecha:todas")])
        botones.append([InlineKeyboardButton("⬅️ Menú", callback_data="menu")])
        await query.message.reply_text(
            f"📸 *{len(fotos)} fotos guardadas*\n¿De qué fecha?",
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup(botones)
        )

    elif data.startswith('fotos_fecha:'):
        filtro = data[len('fotos_fecha:'):]
        fotos  = load_data().get("trade_fotos", [])
        if filtro != "todas":
            fotos = [f for f in fotos if f["fecha"].startswith(filtro)]
        if not fotos:
            await query.message.reply_text("No hay fotos para esa fecha.")
            return
        await query.message.reply_text(f"📸 {len(fotos)} foto(s):")
        for foto in fotos[-10:]:
            cap   = foto.get("caption", "")
            fecha = foto.get("fecha", "")
            texto = f"📅 {fecha}" + (f"\n{cap}" if cap else "")
            try:
                await query.message.reply_photo(photo=foto["file_id"], caption=texto)
            except Exception as e:
                logger.error(f"Error enviando foto trade: {e}")

    elif data == 'notas':
        notas = load_data().get("notas", [])
        await query.message.reply_text(mostrar_notas(notas), parse_mode='MarkdownV2', reply_markup=menu_keyboard())

    elif data == 'sofia_modo':
        set_sofia_mode(True)
        await query.message.reply_text(
            "Hola Raúl. Soy Sofía, tu psicóloga.\n\n"
            "Este es tu espacio seguro — puedes hablarme de lo que sea, sin filtros ni juicios. "
            "Estoy aquí para escucharte y acompañarte.\n\n"
            "¿Qué tienes en la mente?"
        )

    elif data in ('hab_si', 'hab_no'):
        d  = load_data()
        hf = d.get("habito_flow")
        if not hf:
            await query.answer("No hay check-in activo."); return
        paso       = hf["paso"]
        respuestas = hf["respuestas"]
        clave, pregunta_text = HABITOS[paso]
        respuesta_bool = (data == 'hab_si')
        respuestas[clave] = respuesta_bool
        short = pregunta_text.split("¿")[-1].rstrip("?").strip() if "¿" in pregunta_text else pregunta_text
        await query.message.edit_text(
            f"_{escape_md(short)}_: *{'Sí ✅' if respuesta_bool else 'No ❌'}*",
            parse_mode='MarkdownV2'
        )
        siguiente = paso + 1
        if siguiente < len(HABITOS):
            set_habito_flow(siguiente, respuestas)
            _, prox = HABITOS[siguiente]
            await query.message.reply_text(f"*{escape_md(prox)}*", parse_mode='MarkdownV2', reply_markup=habito_keyboard())
        else:
            registrar_habito(respuestas)
            cumplidos  = sum(1 for v in respuestas.values() if v)
            total      = len(HABITOS)
            emoji      = "🔥" if cumplidos == total else "💪" if cumplidos >= 2 else "😤"
            streaks    = get_streaks()
            streak_txt = streak_text(streaks)
            frase      = frase_aleatoria()
            txt = f"✅ *Hábitos del día guardados\\. {cumplidos}/{total} {emoji}*\n\n"
            if streak_txt:
                txt += f"{streak_txt}\n"
            txt += f"_{frase}_"
            await query.message.reply_text(txt, parse_mode='MarkdownV2')

    elif data == 'accion_si':
        action = get_pending_action()
        if not action: return
        clear_pending_action()
        if action["type"] == "gasto":
            cat       = registrar_gasto(action["amount"], action["category"])
            total_cat = sum(g["cantidad"] for g in get_gastos_mes() if g["categoria"] == cat)
            presup    = PRESUPUESTO.get(cat)
            cat_esc   = escape_md(cat.capitalize())
            pct_txt   = f" \\({total_cat/presup*100:.0f}% del mes\\)" if presup else ""
            await query.message.reply_text(
                f"✅ *${action['amount']:.0f} en {cat_esc} registrado*\n_{cat_esc} este mes: ${total_cat:.0f}{pct_txt}_",
                parse_mode='MarkdownV2'
            )
            alert = check_budget_alert(cat)
            if alert:
                await query.message.reply_text(alert, parse_mode='MarkdownV2')
        elif action["type"] == "ingreso":
            registrar_ingreso(action["amount"], action.get("tipo", "otro"))
            monto_esc = escape_md(f"${action['amount']:,.0f}")
            tipo_esc  = escape_md(action.get("tipo", "otro").capitalize())
            await query.message.reply_text(
                f"✅ *{monto_esc} registrado como ingreso*\n_{tipo_esc}_",
                parse_mode='MarkdownV2'
            )
        elif action["type"] == "movimiento":
            registrar_movimiento(action["amount"], action.get("descripcion", "movimiento"))
            monto_esc = escape_md(f"${action['amount']:,.0f}")
            desc_esc  = escape_md(action.get("descripcion", "movimiento"))
            await query.message.reply_text(
                f"✅ *{monto_esc} movimiento entre cuentas registrado*\n_{desc_esc}_",
                parse_mode='MarkdownV2'
            )

    elif data == 'accion_no':
        clear_pending_action()
        await query.answer("Ok, no se registró nada.")

    elif data == 'trade_si':
        tp = get_trade_pending()
        if not tp: return
        if tp["type"] == "entry":
            trade = {
                "fecha_entrada": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
                "par":           tp["data"].get("par", "?"),
                "direccion":     tp["data"].get("direccion", "?"),
                "entrada":       tp["data"].get("entrada"),
                "sl":            tp["data"].get("sl"),
                "tp":            tp["data"].get("tp"),
                "fecha_salida":  None,
            }
            guardar_trade_entrada(trade)
            clear_trade_pending()
            par_esc  = escape_md(trade["par"])
            dire_esc = escape_md(trade["direccion"])
            await query.message.edit_text(
                f"✅ *Trade registrado*\n_{par_esc} {dire_esc} — esperando salida\\._\n\n"
                f"_Cuando cierres, manda foto con caption_ `salida`",
                parse_mode='MarkdownV2'
            )
        elif tp["type"] == "exit":
            clear_trade_pending()
            # Guardar salida temporal en trade_pending para usarla después de emoción
            d = load_data()
            d["trade_pending"] = {"type": "exit_emo", "salida": tp["salida"], "fecha_entrada": tp["fecha_entrada"]}
            save_data(d)
            await query.message.edit_text(
                "¿Cómo salió el trade?",
                reply_markup=emocion_trade_keyboard()
            )

    elif data == 'trade_no':
        clear_trade_pending()
        await query.message.edit_text("Entendido, descartado. Manda la foto de nuevo cuando quieras.")

    elif data.startswith('trade_emo_'):
        emocion = data[len('trade_emo_'):]
        tp = get_trade_pending()
        if not tp or tp.get("type") != "exit_emo": return
        d = load_data()
        d["trade_pending"]["emocion"] = emocion
        save_data(d)
        await query.message.edit_text(
            "¿Seguiste tu estrategia en este trade?",
            reply_markup=estrategia_keyboard()
        )

    elif data in ('trade_plan_si', 'trade_plan_no'):
        tp = get_trade_pending()
        if not tp or tp.get("type") != "exit_emo": return
        siguio_plan = (data == 'trade_plan_si')
        cerrar_trade(
            tp["fecha_entrada"],
            tp["salida"],
            tp.get("emocion", "?"),
            siguio_plan
        )
        clear_trade_pending()

        # Mostrar resumen del trade
        trades = load_data().get("trades", [])
        trade  = next((t for t in reversed(trades) if t.get("fecha_entrada") == tp["fecha_entrada"]), None)
        r_val  = trade.get("resultado_r") if trade else None
        r_txt  = escape_md(f"{r_val:+.2f}R") if r_val is not None else "sin SL registrado"
        emoji  = "✅" if (r_val or 0) > 0 else "🔴" if r_val is not None else "📊"
        plan_txt = "Sí" if siguio_plan else "No"
        await query.message.edit_text(
            f"{emoji} *Trade cerrado*\n\n"
            f"Resultado: *{r_txt}*\n"
            f"Emoción: {escape_md(tp.get('emocion','?'))}\n"
            f"¿Siguió el plan?: {plan_txt}\n\n"
            f"_{frase_aleatoria()}_",
            parse_mode='MarkdownV2'
        )

    elif data.startswith('gt:'):
        # Nivel 1 Gmail: Gasto / Ingreso / Movimiento / Ignorar
        parts = data.split(':', 2)
        if len(parts) < 3:
            return
        short_id = parts[1]
        tipo     = parts[2]

        d = load_data()
        pending = d.get("gmail_pending", {})
        tx = pending.get(short_id)
        if not tx:
            await query.answer("Ya procesado.")
            return

        monto   = tx.get("monto", 0)
        comercio = tx.get("comercio", "")

        if tipo == "ignorar":
            pending.pop(short_id, None)
            d["gmail_pending"] = pending
            save_data(d)
            await query.message.edit_text("❌ _Ignorado\\._", parse_mode='MarkdownV2')

        elif tipo == "movimiento":
            # Hacer todo en una sola transacción para evitar sobreescritura
            d.setdefault("movimientos", [])
            d["movimientos"].append({
                "fecha":       datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
                "cantidad":    float(monto),
                "descripcion": comercio or tx.get("descripcion", "movimiento"),
            })
            pending.pop(short_id, None)
            d["gmail_pending"] = pending
            save_data(d)
            await query.message.edit_text(
                f"🔄 *Movimiento registrado*\n_{escape_md(f'${monto:,.2f}')} entre cuentas_",
                parse_mode='MarkdownV2'
            )

        elif tipo == "ingreso":
            # Mostrar sub-teclado para clasificar el tipo de ingreso
            pending.pop(short_id, None)
            d["gmail_pending"] = pending
            # Guardar temporalmente el monto en un campo especial para el sub-paso
            d.setdefault("gmail_ingreso_pending", {})
            d["gmail_ingreso_pending"][short_id] = {"monto": monto, "comercio": comercio, "descripcion": tx.get("descripcion", "")}
            save_data(d)
            monto_esc = escape_md(f"${monto:,.2f}")
            await query.message.edit_text(
                f"💰 *{monto_esc}* — ¿Qué tipo de ingreso fue?",
                parse_mode='MarkdownV2',
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🏠 Renta",           callback_data=f"gi:{short_id}:renta"),
                        InlineKeyboardButton("🔄 Transferencia",   callback_data=f"gi:{short_id}:transferencia"),
                    ],
                    [
                        InlineKeyboardButton("📈 Rendimientos",    callback_data=f"gi:{short_id}:rendimientos"),
                        InlineKeyboardButton("💼 Otro",            callback_data=f"gi:{short_id}:otro"),
                    ],
                ])
            )

        elif tipo == "gasto":
            # Pedir descripción en texto
            d["gmail_awaiting_desc"] = {"short_id": short_id, "monto": monto, "comercio": comercio}
            d["gmail_pending"] = pending
            save_data(d)
            comercio_txt = f" en *{escape_md(comercio)}*" if comercio and comercio != "desconocido" else ""
            await query.message.edit_text(
                f"💸 *{escape_md(f'${monto:,.2f}')}*{comercio_txt}\n\n"
                f"¿Qué fue? Descríbelo en texto \\(ej: _tacos con el abuelo_, _super semanal_\\)",
                parse_mode='MarkdownV2'
            )

    elif data.startswith('gi:'):
        # Nivel 2 Gmail: tipo de ingreso seleccionado
        parts = data.split(':', 2)
        if len(parts) < 3:
            return
        short_id     = parts[1]
        tipo_ingreso = parts[2]

        d = load_data()
        # Buscar en gmail_ingreso_pending (flujo nuevo) o gmail_pending (flujo viejo)
        ip = d.get("gmail_ingreso_pending", {})
        tx = ip.get(short_id)
        if not tx:
            # fallback: buscar en gmail_pending por compatibilidad
            tx = d.get("gmail_pending", {}).get(short_id)
        if not tx:
            await query.answer("Ya procesado.")
            return

        monto = tx.get("monto", 0)
        desc  = tx.get("comercio", "") or tx.get("descripcion", "")

        # Todo en una sola transacción — sin llamar a registrar_ingreso para evitar sobreescritura
        d.setdefault("ingresos", [])
        d["ingresos"].append({
            "fecha":       datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
            "cantidad":    float(monto),
            "tipo":        tipo_ingreso,
            "descripcion": desc,
        })
        # Limpiar pending de ambos flujos
        ip.pop(short_id, None)
        d["gmail_ingreso_pending"] = ip
        gp = d.get("gmail_pending", {})
        gp.pop(short_id, None)
        d["gmail_pending"] = gp
        save_data(d)

        tipos_label = {"renta": "Renta", "transferencia": "Transferencia recibida",
                       "rendimientos": "Rendimientos", "otro": "Otro ingreso"}
        label = escape_md(tipos_label.get(tipo_ingreso, tipo_ingreso.capitalize()))
        monto_esc = escape_md(f"${monto:,.2f}")
        await query.message.edit_text(
            f"✅ *Ingreso registrado*\n_{monto_esc} — {label}_",
            parse_mode='MarkdownV2'
        )

    elif data.startswith('gc:'):
        # Nivel 2 Gmail: cambiar categoría de gasto manualmente
        parts = data.split(':', 2)
        if len(parts) < 3:
            return
        short_id  = parts[1]
        categoria = parts[2]

        d = load_data()
        pending = d.get("gmail_pending", {})
        tx = pending.get(short_id)
        if not tx:
            await query.answer("Ya procesado.")
            return

        monto = tx.get("monto", 0)
        comercio = tx.get("comercio", "")

        if categoria == '_skip':
            pending.pop(short_id, None)
            d["gmail_pending"] = pending
            save_data(d)
            await query.message.edit_text("❌ _Ignorado\\._", parse_mode='MarkdownV2')
            return

        # Todo en una sola transacción para evitar sobreescritura
        cat_normalizada = CATEGORIAS_ALIAS.get(categoria.lower(), categoria.lower())
        d.setdefault("gastos", [])
        d["gastos"].append({
            "fecha":     datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
            "cantidad":  float(monto),
            "categoria": cat_normalizada,
            "comercio":  comercio,
        })
        pending.pop(short_id, None)
        d["gmail_pending"] = pending
        save_data(d)
        cat_esc   = escape_md(cat_normalizada.capitalize())
        monto_esc = escape_md(f"${monto:,.2f}")
        await query.message.edit_text(
            f"✅ *{monto_esc} en {cat_esc} registrado*",
            parse_mode='MarkdownV2'
        )
        # Alertas de presupuesto
        presup = PRESUPUESTO.get(cat_normalizada)
        if presup:
            total_cat = sum(g["cantidad"] for g in d.get("gastos", [])
                           if g["categoria"] == cat_normalizada
                           and g["fecha"].startswith(datetime.now(TIMEZONE).strftime("%Y-%m")))
            pct = total_cat / presup * 100
            if pct >= 100:
                await query.message.reply_text(
                    f"🚨 *¡Superaste el presupuesto de {cat_esc}\\!*\n_${total_cat:.0f} de ${presup} \\({pct:.0f}%\\)_",
                    parse_mode='MarkdownV2'
                )
            elif pct >= 80:
                await query.message.reply_text(
                    f"⚠️ *Alerta: {cat_esc} al {pct:.0f}%*\n_${total_cat:.0f} de ${presup}_",
                    parse_mode='MarkdownV2'
                )
        alert = check_budget_alert(categoria)
        if alert:
            await query.message.reply_text(alert, parse_mode='MarkdownV2')

# ------------------------------------
# HANDLER DE MENSAJES
# ------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_text_message(update, context, update.message.text or "")

# ------------------------------------
# JOBS PROGRAMADOS
# ------------------------------------

async def job_semanal(context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id()
    if not chat_id: return
    await context.bot.send_message(chat_id, generar_resumen_semanal(), parse_mode='MarkdownV2')
    set_flow('semanal', 0, [])
    await enviar_pregunta(context.bot, chat_id, 'semanal', 0)

async def job_mensual(context: ContextTypes.DEFAULT_TYPE):
    if es_ultimo_viernes():
        chat_id = get_chat_id()
        if chat_id:
            set_flow('mensual', 0, [])
            await enviar_pregunta(context.bot, chat_id, 'mensual', 0)

async def job_capital(context: ContextTypes.DEFAULT_TYPE):
    if dia_hoy() == 1:
        chat_id = get_chat_id()
        if chat_id:
            await context.bot.send_message(
                chat_id,
                mostrar_balance_mes(),
                parse_mode='MarkdownV2',
            )

async def job_pedir_informe(context: ContextTypes.DEFAULT_TYPE):
    if dia_hoy() == 30:
        chat_id = get_chat_id()
        if chat_id:
            await context.bot.send_message(chat_id, PEDIR_INFORME, parse_mode='MarkdownV2')

async def job_enviar_informe(context: ContextTypes.DEFAULT_TYPE):
    if dia_hoy() == 4:
        chat_id = get_chat_id()
        if chat_id:
            await context.bot.send_message(chat_id, ENVIAR_INFORME, parse_mode='MarkdownV2')

async def job_habitos(context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id()
    if not chat_id: return
    set_habito_flow(0, {})
    _, primera = HABITOS[0]
    await context.bot.send_message(
        chat_id,
        f"🌙 *RAÚL — CHECK\\-IN DIARIO*\n━━━━━━━━━━━━━━━\n\n*{escape_md(primera)}*",
        parse_mode='MarkdownV2', reply_markup=habito_keyboard()
    )

async def job_reporte_mensual(context: ContextTypes.DEFAULT_TYPE):
    """Día 1 de cada mes a las 9am: reporte global del mes anterior."""
    if dia_hoy() != 1:
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    try:
        reporte = generar_reporte_global_mensual()
        await context.bot.send_message(chat_id, reporte, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"job_reporte_mensual error: {e}")

async def job_reporte_sofia_mensual(context: ContextTypes.DEFAULT_TYPE):
    """Día 1 de cada mes a las 9pm: análisis emocional de Sofía del mes anterior."""
    if dia_hoy() != 1:
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    if not os.environ.get("GROQ_API_KEY"):
        return
    try:
        reporte = await asyncio.to_thread(_generar_reporte_sofia_mensual_sync)
        if not reporte:
            return
        intro = (
            "🧠 *RAÚL — REPORTE EMOCIONAL MENSUAL \\(Sofía\\)*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        await context.bot.send_message(
            chat_id,
            intro + escape_md(reporte),
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"job_reporte_sofia_mensual error: {e}")

async def job_reflexion_mensual_dia1(context: ContextTypes.DEFAULT_TYPE):
    """Día 1 de cada mes a las 9:30pm: inicia el flujo de reflexión mensual."""
    if dia_hoy() != 1:
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    set_flow('mensual', 0, [])
    await enviar_pregunta(context.bot, chat_id, 'mensual', 0)

async def job_reporte_anual(context: ContextTypes.DEFAULT_TYPE):
    """1 de enero: reporte anual emocional + financiero."""
    now = datetime.now(TIMEZONE)
    if now.month != 1 or now.day != 1:
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    año_anterior = now.year - 1
    if not os.environ.get("GROQ_API_KEY"):
        return
    try:
        # Reporte emocional anual
        rep_emocional = await asyncio.to_thread(_generar_reporte_sofia_anual_sync, año_anterior)
        if rep_emocional:
            intro = (
                f"🌅 *RAÚL — REPORTE ANUAL EMOCIONAL {año_anterior} \\(Sofía\\)*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            await context.bot.send_message(
                chat_id,
                intro + escape_md(rep_emocional),
                parse_mode='MarkdownV2'
            )

        # Reporte financiero anual
        rep_financiero = await asyncio.to_thread(_generar_reporte_financiero_anual_sync, año_anterior)
        if rep_financiero:
            intro2 = (
                f"💰 *RAÚL — REPORTE FINANCIERO ANUAL {año_anterior}*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            await context.bot.send_message(
                chat_id,
                intro2 + escape_md(rep_financiero),
                parse_mode='MarkdownV2'
            )
    except Exception as e:
        logger.error(f"job_reporte_anual error: {e}")

# ------------------------------------
# GOOGLE CALENDAR
# ------------------------------------

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


# ------------------------------------
# GMAIL — DETECCIÓN DE TRANSACCIONES
# ------------------------------------

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


def gmail_tipo_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Nivel 1: ¿Qué tipo de movimiento fue?"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💸 Fue un gasto",    callback_data=f"gt:{short_id}:gasto"),
            InlineKeyboardButton("💰 Ingresó dinero",  callback_data=f"gt:{short_id}:ingreso"),
        ],
        [
            InlineKeyboardButton("🔄 Moví dinero",     callback_data=f"gt:{short_id}:movimiento"),
            InlineKeyboardButton("❌ Ignorar",          callback_data=f"gt:{short_id}:ignorar"),
        ],
    ])

def gmail_ingreso_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Nivel 2 para ingresos: ¿De dónde vino?"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏠 Renta",              callback_data=f"gi:{short_id}:renta"),
            InlineKeyboardButton("👤 Transferencia",       callback_data=f"gi:{short_id}:transferencia"),
        ],
        [
            InlineKeyboardButton("📈 Rendimientos",        callback_data=f"gi:{short_id}:rendimientos"),
            InlineKeyboardButton("📦 Otro ingreso",        callback_data=f"gi:{short_id}:otro"),
        ],
    ])

def gmail_cambiar_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Nivel 2 para gastos: seleccionar categoría manualmente."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍽 Comida",      callback_data=f"gc:{short_id}:comida"),
            InlineKeyboardButton("🚌 Transporte",  callback_data=f"gc:{short_id}:transporte"),
        ],
        [
            InlineKeyboardButton("💊 Salud",       callback_data=f"gc:{short_id}:salud"),
            InlineKeyboardButton("🎉 Capricho",    callback_data=f"gc:{short_id}:capricho"),
        ],
        [
            InlineKeyboardButton("📦 Otros",       callback_data=f"gc:{short_id}:otros"),
            InlineKeyboardButton("❌ Ignorar",      callback_data=f"gc:{short_id}:_skip"),
        ],
    ])


# ------------------------------------
# NOTICIAS FOREX — ALTO IMPACTO (TradingView Economic Calendar)
# -------------------------------------------------------------

# Códigos de monedas principales para filtrar
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


def _split_text(text, max_len=4000):
    """Divide texto en chunks respetando saltos de línea."""
    lines = text.split("\n")
    chunks, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > max_len:
            chunks.append(cur.rstrip())
            cur = line + "\n"
        else:
            cur += line + "\n"
    if cur.strip():
        chunks.append(cur.rstrip())
    return chunks


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


async def cmd_noticias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra noticias de alto impacto. Args: mañana | semana"""
    arg = " ".join(context.args).strip().lower() if context.args else ""
    mx  = TIMEZONE
    now = datetime.now(mx)

    if arg in ("semana", "week", "esta semana"):
        # Lunes de la semana actual
        monday = now.date() - timedelta(days=now.weekday())
        target = monday
        label  = f"semana {monday.strftime('%d/%m')}–{(monday + timedelta(days=4)).strftime('%d/%m')}"
        days   = 7
    elif arg in ("mañana", "manana", "tomorrow"):
        target = (now + timedelta(days=1)).date()
        label  = "mañana"
        days   = 1
    else:
        target = now.date()
        label  = now.strftime("%A %d/%m")
        days   = 1

    msg = await update.message.reply_text("🔍 Consultando calendario económico...")
    try:
        await _send_noticias(None, None, target, label, days, edit_msg=msg)
    except asyncio.TimeoutError:
        await msg.edit_text("⏱ El calendario tardó demasiado. Intenta de nuevo.")
    except Exception as e:
        logger.error(f"cmd_noticias error: {e}")
        await msg.edit_text(f"❌ Error: {e}")


async def job_forex_news(context: ContextTypes.DEFAULT_TYPE):
    """Job diario: manda noticias de alto impacto a las 6am México."""
    chat_id = get_chat_id()
    if not chat_id:
        return
    mx     = TIMEZONE
    target = datetime.now(mx).date()
    label  = datetime.now(mx).strftime("%A %d/%m")
    try:
        await _send_noticias(context.bot, chat_id, target, label, days=1)
    except Exception as e:
        logger.error(f"job_forex_news error: {e}")


async def job_gmail_check(context: ContextTypes.DEFAULT_TYPE, window_hours: float = 2):
    """Corre cada 30 minutos. Lee los dos correos y manda notificaciones de nuevas transacciones."""
    tokens = {
        "1": os.environ.get("GMAIL_REFRESH_TOKEN_1", ""),
        "2": os.environ.get("GMAIL_REFRESH_TOKEN_2", ""),
    }
    client_id = os.environ.get("GMAIL_CLIENT_ID", "")
    logger.info(f"Gmail job: client_id={'SET' if client_id else 'MISSING'}, tokens={{'1': {'SET' if tokens['1'] else 'MISSING'}, '2': {'SET' if tokens['2'] else 'MISSING'}}}")
    if not client_id:
        logger.warning("Gmail job: GMAIL_CLIENT_ID no configurado, saltando")
        return

    chat_id = get_chat_id()
    logger.info(f"Gmail job: chat_id={chat_id}")
    if not chat_id:
        logger.warning("Gmail job: chat_id no encontrado, saltando")
        return

    data = load_data()
    processed_ids: set = set(data.get("gmail_processed_ids", []))
    pending: dict      = data.get("gmail_pending", {})

    new_found = False
    for account_num, refresh_token in tokens.items():
        if not refresh_token:
            continue
        try:
            txs = await asyncio.to_thread(_fetch_gmail_transactions_sync, refresh_token, None, window_hours)
        except Exception as e:
            logger.error(f"Gmail check account {account_num} error: {e}")
            continue

        for tx in txs:
            eid = tx["email_id"]
            if eid in processed_ids:
                continue

            # Guardar como pendiente
            short_id      = eid[-12:]
            pending[short_id] = tx
            processed_ids.add(eid)
            new_found = True

            monto    = tx.get("monto", 0)
            comercio = tx.get("comercio", tx.get("descripcion", tx.get("subject", "?"))[:40])
            cuenta_txt = escape_md(f"cuenta {account_num}")

            msg = (
                f"📬 *Movimiento detectado* \\({cuenta_txt}\\)\n"
                f"━━━━━━━━━━━━━━━\n"
                f"*{escape_md(f'${monto:,.2f}')}*"
                + (f" — {escape_md(comercio)}" if comercio and comercio != "desconocido" else "")
                + f"\n\n¿Qué fue esto?"
            )
            await context.bot.send_message(chat_id, msg, parse_mode='MarkdownV2',
                                           reply_markup=gmail_tipo_keyboard(short_id))

    # Guardar estado actualizado — mantener solo los últimos 500 IDs procesados
    processed_list = list(processed_ids)[-500:]
    data["gmail_processed_ids"] = processed_list
    data["gmail_pending"]       = pending
    save_data(data)


# ------------------------------------
# PESO / MEDIDAS
# ------------------------------------

def _formato_peso(registros):
    if not registros:
        return "No hay registros de peso.\nUso: /peso 78.5"
    ultimos = registros[-12:]  # últimos 12 registros
    vals = [r["valor"] for r in ultimos]
    minv, maxv = min(vals), max(vals)
    rango = maxv - minv if maxv != minv else 1
    WIDTH = 20
    lines = ["📊 *Peso — historial*\n"]
    for r in ultimos:
        fecha = r["fecha"][5:]  # MM-DD
        v = r["valor"]
        bar_len = int((v - minv) / rango * WIDTH) if rango else WIDTH // 2
        bar = "█" * bar_len + "░" * (WIDTH - bar_len)
        lines.append(f"`{fecha}` {bar} *{v:.1f} kg*")
    if len(vals) >= 2:
        diff = vals[-1] - vals[0]
        trend = f"{'▼' if diff < 0 else '▲'} {abs(diff):.1f} kg vs primer registro"
        lines.append(f"\n_{trend}_")
    return "\n".join(lines)


async def cmd_peso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra o muestra historial de peso. /peso 78.5"""
    if not context.args:
        d = load_data()
        texto = _formato_peso(d.get("peso", []))
        await update.message.reply_text(texto, parse_mode='MarkdownV2')
        return
    try:
        valor = float(context.args[0].replace(',', '.'))
    except ValueError:
        await update.message.reply_text("Uso: /peso 78.5")
        return
    d = load_data()
    if "peso" not in d:
        d["peso"] = []
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    d["peso"] = [p for p in d["peso"] if p["fecha"] != fecha]
    d["peso"].append({"fecha": fecha, "valor": valor})
    d["peso"].sort(key=lambda x: x["fecha"])
    # Auto-update calorie target
    nueva_meta = _calcular_meta_calorias(valor)
    meta_anterior = d.get("meta_calorias", META_CAL_BASE)
    d["meta_calorias"] = nueva_meta
    save_data(d)
    texto = _formato_peso(d["peso"])
    await update.message.reply_text(texto, parse_mode='MarkdownV2')
    if nueva_meta != meta_anterior:
        await update.message.reply_text(
            f"⚡ *Meta de calorías actualizada:* {nueva_meta} kcal/día",
            parse_mode='MarkdownV2'
        )


async def cmd_salud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dashboard de salud: peso + pasos + calorías."""
    s = get_salud_hoy()
    sem = get_salud_semana()
    d = load_data()
    pesos = d.get("peso", [])
    peso_txt = f"{s['peso']:.1f} kg" if s["peso"] else "no registrado"
    meta_cal = s["meta_calorias"]

    pasos_hoy = f"{s['pasos']:,}" if s["pasos"] else "—"
    cal_hoy   = f"{s['calorias']} kcal" if s["calorias"] else "—"
    pasos_pct = f" \\({round(s['pasos']/META_PASOS_DIARIO*100)}%\\)" if s["pasos"] else ""
    cal_pct   = ""

    avg_p = f"{sem['avg_pasos']:,}" if sem["avg_pasos"] else "—"
    avg_c = f"{sem['avg_calorias']} kcal" if sem["avg_calorias"] else "—"

    # Tendencia peso
    trend = ""
    if len(pesos) >= 2:
        diff = pesos[-1]["valor"] - pesos[0]["valor"]
        trend = f"\n  Tendencia: {'▼' if diff < 0 else '▲'} {abs(diff):.1f} kg vs inicio"

    texto = (
        "💪 *SALUD & FITNESS — HOY*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"⚖️ *Peso:* {escape_md(peso_txt)}{escape_md(trend)}\n"
        f"  Meta calorías: {meta_cal} kcal/día\n\n"
        f"👟 *Pasos:* {escape_md(pasos_hoy)}{pasos_pct}\n"
        f"  Meta: {META_PASOS_DIARIO:,} pasos/día\n\n"
        f"🔥 *Calorías quemadas:* {escape_md(cal_hoy)}{escape_md(cal_pct)}\n\n"
        "━━━━━━━━━━━━━━━\n"
        f"📊 *Promedio últimos 7 días:*\n"
        f"  Pasos: {escape_md(avg_p)} \\({sem['dias_pasos']} días con datos\\)\n"
        f"  Calorías: {escape_md(avg_c)}\n\n"
        "_Registra vía: 'hice 8000 pasos' o 'quemé 350 cal'_"
    )
    await update.message.reply_text(texto, parse_mode='MarkdownV2')


async def cmd_rutina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la rutina de entrenamiento L/M/V."""
    hoy = datetime.now(TIMEZONE).weekday()
    dias_gym = {0: "LUNES", 2: "MIÉRCOLES", 4: "VIERNES"}
    dia_gym = dias_gym.get(hoy)
    if dia_gym:
        header = f"🏋️ *RUTINA DE HOY — {dia_gym}*\n"
    else:
        proximo = min((d for d in dias_gym if d > hoy), default=0)
        header = f"🏋️ *RUTINA PRÓXIMO DÍA \\(L/M/V\\)*\n"

    lineas = ["━━━━━━━━━━━━━━━\n"]
    for titulo, desc in RUTINA_LMV:
        lineas.append(f"*{escape_md(titulo)}*\n_{escape_md(desc)}_\n")
    lineas.append("━━━━━━━━━━━━━━━")
    lineas.append("_Horario scalper: lunes a viernes 7\\-10am_")
    lineas.append("_Análisis semanal: viernes 12:45\\-1:30pm_")
    await update.message.reply_text(header + "\n".join(lineas), parse_mode='MarkdownV2')


# ------------------------------------
# BACKUP SEMANAL
# ------------------------------------

async def job_backup_semanal(context: ContextTypes.DEFAULT_TYPE):
    """Domingo 9pm México — manda registro.json como documento."""
    if datetime.now(TIMEZONE).weekday() != 6:  # 6 = domingo
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    data_path = os.path.join(DATA_DIR, "registro.json")
    if not os.path.exists(data_path):
        return
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    with open(data_path, 'rb') as f:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=f"registro_backup_{fecha}.json",
            caption=f"💾 Backup semanal — {fecha}"
        )


# ------------------------------------
# JOBS — TRADING & SALUD
# ------------------------------------

async def job_aviso_scalper(context: ContextTypes.DEFAULT_TYPE):
    """Lun-Vie 6:45am — aviso sesión scalper 7-10am."""
    hoy = datetime.now(TIMEZONE).weekday()
    if hoy > 4:  # sábado o domingo
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    await context.bot.send_message(
        chat_id,
        "📈 *SESIÓN SCALPER — 7:00am*\n\n"
        "Tienes 15 minutos para prepararte\\.\n"
        "Horario: 7:00 \\- 10:00am\n\n"
        "_Respira\\. Estrategia\\. Sin apuro\\._",
        parse_mode='MarkdownV2'
    )


async def job_aviso_analisis_semanal(context: ContextTypes.DEFAULT_TYPE):
    """Viernes 12:30pm — aviso análisis de temporalidad 12:45-1:30pm."""
    if datetime.now(TIMEZONE).weekday() != 4:  # solo viernes
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    await context.bot.send_message(
        chat_id,
        "🔭 *ANÁLISIS SEMANAL — 12:45pm*\n\n"
        "En 15 minutos: análisis de temporalidad\\.\n"
        "Índices, acciones y mercado en general\\.\n"
        "Duración: 45 min \\(12:45 \\- 1:30pm\\)\n\n"
        "_Prepara tu setup\\. Es tu ventaja del fin de semana\\._",
        parse_mode='MarkdownV2'
    )


async def job_aviso_corte_cabello(context: ContextTypes.DEFAULT_TYPE):
    """Sábados — avisa si le toca corte cada 2 semanas."""
    if datetime.now(TIMEZONE).weekday() != 5:  # solo sábado
        return
    if not es_semana_corte():
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    await context.bot.send_message(
        chat_id,
        "✂️ *HOY TOCA CORTE DE CABELLO*\n\n"
        "_Semana sí — agenda tu cita hoy\\._",
        parse_mode='MarkdownV2'
    )


# ------------------------------------
# RECORDATORIOS
# ------------------------------------

def guardar_recordatorio(fecha_iso, mensaje, repetir=None):
    import uuid
    data = load_data()
    data.setdefault("recordatorios", [])
    data["recordatorios"].append({
        "id": str(uuid.uuid4())[:8],
        "fecha": fecha_iso,
        "mensaje": mensaje,
        "repetir": repetir,
        "activo": True,
    })
    save_data(data)

def eliminar_recordatorio(rid):
    data = load_data()
    data["recordatorios"] = [r for r in data.get("recordatorios", []) if r["id"] != rid]
    save_data(data)

def _parse_recordatorio(text):
    """Intenta parsear fecha/hora y mensaje de un texto natural en español.
    Retorna (fecha_iso, repetir, mensaje) o None."""
    tl = text.lower()
    mx = TIMEZONE
    now = datetime.now(mx)

    time_re = re.compile(
        r'a\s+las\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?|(\d{1,2})(?::(\d{2}))?\s*(am|pm)',
        re.IGNORECASE
    )
    time_m = time_re.search(tl)
    if not time_m:
        return None
    g = time_m.groups()
    if g[0]:
        h_raw, m_str, ampm = int(g[0]), g[1], g[2]
    else:
        h_raw, m_str, ampm = int(g[3]), g[4], g[5]
    minute = int(m_str) if m_str else 0
    if ampm and ampm.lower() == 'pm' and h_raw < 12:
        h_raw += 12
    elif ampm and ampm.lower() == 'am' and h_raw == 12:
        h_raw = 0
    if h_raw > 23:
        return None

    days_map = {
        'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2,
        'jueves': 3, 'viernes': 4, 'sábado': 5, 'sabado': 5, 'domingo': 6,
    }
    target_date = None
    repetir = None

    en_horas_m = re.search(r'en\s+(\d+)\s+horas?', tl)
    if en_horas_m:
        target_dt_raw = now + timedelta(hours=int(en_horas_m.group(1)))
        fecha_iso = target_dt_raw.strftime("%Y-%m-%dT%H:%M")
        msg = _limpiar_msg_recordatorio(text)
        return (fecha_iso, None, msg)

    if 'mañana' in tl or 'manana' in tl:
        target_date = (now + timedelta(days=1)).date()
    elif 'hoy' in tl or 'esta noche' in tl:
        target_date = now.date()
    elif re.search(r'cada\s+d[ií]a|diario|todos\s+los\s+d[ií]as', tl):
        target_date = now.date()
        repetir = 'diario'
    else:
        cada_m = re.search(
            r'cada\s+(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)', tl
        )
        if cada_m:
            raw = cada_m.group(1).lower()
            key = raw.replace('é','e').replace('á','a')
            wd = days_map.get(raw) or days_map.get(key)
            repetir = raw
            if wd is not None:
                days_ahead = (wd - now.weekday()) % 7 or 7
                target_date = (now + timedelta(days=days_ahead)).date()
        else:
            for day_key, wd in days_map.items():
                if day_key in tl:
                    days_ahead = (wd - now.weekday()) % 7 or 7
                    target_date = (now + timedelta(days=days_ahead)).date()
                    break

    if target_date is None:
        return None

    try:
        target_dt = mx.localize(datetime.combine(target_date, dt_time(h_raw, minute)))
    except Exception:
        return None

    if target_dt <= now and repetir is None:
        return None

    msg = _limpiar_msg_recordatorio(text)
    return (target_dt.strftime("%Y-%m-%dT%H:%M"), repetir, msg)


def _limpiar_msg_recordatorio(text):
    msg = re.sub(
        r'(?:recuérdame|recuerdame|pon(?:me)?\s+(?:una\s+)?alarma|alarma\s+para|recordatorio)',
        '', text, flags=re.IGNORECASE
    )
    msg = re.sub(
        r'(?:mañana|manana|hoy|esta\s+noche|el\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)|'
        r'cada\s+(?:d[ií]a|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo))',
        '', msg, flags=re.IGNORECASE
    )
    msg = re.sub(r'a\s+las\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}(?::\d{2})?\s*(?:am|pm)', '', msg, flags=re.IGNORECASE)
    msg = re.sub(r'^\s*(?:que|a que|de que)\s+', '', msg, flags=re.IGNORECASE)
    msg = re.sub(r'\s+', ' ', msg).strip().strip('.,;')
    return msg if msg else "Recordatorio"


async def cmd_recordatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recs = [r for r in load_data().get("recordatorios", []) if r.get("activo", True)]
    if not recs:
        await update.message.reply_text("No tienes recordatorios activos.\n\nEjemplo: _'recuérdame mañana a las 8am ir al banco'_", parse_mode='Markdown')
        return
    lines = ["⏰ *Tus recordatorios activos:*\n"]
    for r in recs:
        try:
            dt = TIMEZONE.localize(datetime.strptime(r["fecha"], "%Y-%m-%dT%H:%M"))
            fecha_fmt = dt.strftime("%a %d/%m a las %H:%M")
        except Exception:
            fecha_fmt = r["fecha"]
        rep_txt = f" _(repite cada {r['repetir']})_" if r.get("repetir") else ""
        lines.append(f"• `{r['id']}` — {fecha_fmt}{rep_txt}\n  {r['mensaje']}")
    lines.append("\nPara eliminar: `/borrar_rec ID`")
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')


async def cmd_borrar_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: `/borrar_rec ID`\n\nUsa /recordatorio para ver los IDs.", parse_mode='Markdown')
        return
    rid = context.args[0]
    eliminar_recordatorio(rid)
    await update.message.reply_text(f"✅ Recordatorio `{rid}` eliminado.", parse_mode='Markdown')


async def job_check_recordatorios(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    recs = data.get("recordatorios", [])
    if not recs:
        return
    now = datetime.now(TIMEZONE)
    chat_id = get_chat_id()
    if not chat_id:
        return
    changed = False
    days_map = {
        'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2,
        'jueves': 3, 'viernes': 4, 'sábado': 5, 'sabado': 5, 'domingo': 6,
    }
    for r in recs:
        if not r.get("activo", True):
            continue
        try:
            fecha_dt = TIMEZONE.localize(datetime.strptime(r["fecha"], "%Y-%m-%dT%H:%M"))
        except ValueError:
            continue
        if now >= fecha_dt:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ *Recordatorio*\n\n{r['mensaje']}",
                parse_mode='Markdown'
            )
            changed = True
            repetir = r.get("repetir")
            if repetir == "diario":
                r["fecha"] = (fecha_dt + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
            elif repetir and repetir in days_map:
                wd = days_map[repetir]
                days_ahead = (wd - fecha_dt.weekday()) % 7 or 7
                r["fecha"] = (fecha_dt + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M")
            else:
                r["activo"] = False
    if changed:
        save_data(data)


# ------------------------------------
# MAIN
# ------------------------------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("menu",      cmd_menu))
    app.add_handler(CommandHandler("reporte",   cmd_reporte))
    app.add_handler(CommandHandler("mensual",   cmd_mensual))
    app.add_handler(CommandHandler("capital",   cmd_capital))
    app.add_handler(CommandHandler("historial", cmd_historial))
    app.add_handler(CommandHandler("gastos",    cmd_gastos))
    app.add_handler(CommandHandler("como_voy",  cmd_como_voy))
    app.add_handler(CommandHandler("trades",      cmd_trades))
    app.add_handler(CommandHandler("fotos_trades", cmd_fotos_trades))
    app.add_handler(CommandHandler("notas",        cmd_notas))
    app.add_handler(CommandHandler("cancelar",     cmd_cancelar))
    app.add_handler(CommandHandler("sofia",        cmd_sofia))
    app.add_handler(CommandHandler("salir",        cmd_salir))
    app.add_handler(CommandHandler("gmail_check",  cmd_gmail_check))
    app.add_handler(CommandHandler("agenda",       cmd_agenda))
    app.add_handler(CommandHandler("cal_debug",    cmd_cal_debug))
    app.add_handler(CommandHandler("noticias",     cmd_noticias))
    app.add_handler(CommandHandler("reporte_mes",  cmd_reporte_mes))
    app.add_handler(CommandHandler("reporte_anual", cmd_reporte_anual))
    app.add_handler(CommandHandler("peso",          cmd_peso))
    app.add_handler(CommandHandler("salud",         cmd_salud))
    app.add_handler(CommandHandler("rutina",        cmd_rutina))
    app.add_handler(CommandHandler("recordatorio",  cmd_recordatorio))
    app.add_handler(CommandHandler("borrar_rec",    cmd_borrar_rec))
    app.add_handler(CommandHandler("test",      cmd_test))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    jq = app.job_queue
    mx = TIMEZONE
    # Retroalimentación semanal — jueves 9:30pm (actualizado de 9:10pm)
    jq.run_daily(job_semanal,        time=dt_time(21, 30, tzinfo=mx), days=(3,), name="semanal")
    # job_mensual removido — reemplazado por job_reflexion_mensual_dia1
    jq.run_daily(job_capital,        time=dt_time(8,  0,  tzinfo=mx),            name="capital")
    jq.run_daily(job_enviar_informe, time=dt_time(8,  0,  tzinfo=mx),            name="enviar_informe")
    jq.run_daily(job_pedir_informe,  time=dt_time(20, 30, tzinfo=mx),            name="pedir_informe")
    jq.run_daily(job_habitos,        time=dt_time(21, 0,  tzinfo=mx),            name="habitos")
    jq.run_daily(job_forex_news,     time=dt_time(6,  0,  tzinfo=mx),            name="forex_news")
    # Día 1 de cada mes:
    jq.run_daily(job_reporte_mensual,         time=dt_time(9,  0,  tzinfo=mx), name="reporte_mensual")
    jq.run_daily(job_reporte_sofia_mensual,   time=dt_time(21, 0,  tzinfo=mx), name="sofia_mensual")
    jq.run_daily(job_reflexion_mensual_dia1,  time=dt_time(21, 30, tzinfo=mx), name="reflexion_mensual")
    # 1 de enero: reporte anual
    jq.run_daily(job_reporte_anual,           time=dt_time(10, 0,  tzinfo=mx), name="reporte_anual")
    # Gmail: revisar cada 5 minutos (reduce consumo de tokens Groq)
    if os.environ.get("GMAIL_CLIENT_ID"):
        jq.run_repeating(job_gmail_check, interval=300, first=30, name="gmail")
    # Backup dominical 9pm
    jq.run_daily(job_backup_semanal, time=dt_time(21, 0, tzinfo=mx), name="backup")
    # Recordatorios: revisar cada minuto
    jq.run_repeating(job_check_recordatorios, interval=60, first=10, name="recordatorios")
    # Scalper: aviso lun-vie 6:45am
    jq.run_daily(job_aviso_scalper, time=dt_time(6, 45, tzinfo=mx), name="scalper")
    # Análisis semanal: viernes 12:30pm
    jq.run_daily(job_aviso_analisis_semanal, time=dt_time(12, 30, tzinfo=mx), name="analisis_semanal")
    # Corte de cabello: sábados 9am (verifica si es la semana)
    jq.run_daily(job_aviso_corte_cabello, time=dt_time(9, 0, tzinfo=mx), name="corte_cabello")

    # Recordatorio del reloj (miércoles 2026-04-30 10am) — solo si no existe
    _data = load_data()
    _data.setdefault("recordatorios", [])
    if not any(r.get("id") == "reloj001" for r in _data["recordatorios"]):
        _data["recordatorios"].append({
            "id": "reloj001",
            "fecha": "2026-04-30T10:00",
            "mensaje": "¿Ya compraste el reloj? Cuando lo tengas dime y lo conectamos al bot ⌚",
            "repetir": None,
            "activo": True,
        })
        save_data(_data)

    logger.info("Bot iniciado. Esperando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
