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
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 División de Capital", callback_data='capital'),
            InlineKeyboardButton("📚 Historial",           callback_data='historial'),
        ],
        [
            InlineKeyboardButton("💸 Gastos del Mes",  callback_data='gastos'),
            InlineKeyboardButton("🎯 ¿Cómo voy?",      callback_data='como_voy'),
        ],
        [
            InlineKeyboardButton("📸 Mis Trades",  callback_data='fotos_trades'),
            InlineKeyboardButton("📝 Notas",        callback_data='notas'),
        ],
        [
            InlineKeyboardButton("🧠 Hablar con Sofía", callback_data='sofia_modo'),
        ],
    ])

def historial_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Semanales", callback_data='hist_semanal'),
            InlineKeyboardButton("🧠 Mensuales", callback_data='hist_mensual'),
        ],
        [
            InlineKeyboardButton("💰 Capital",   callback_data='hist_capital'),
            InlineKeyboardButton("📋 Todo",      callback_data='hist_todo'),
        ],
        [InlineKeyboardButton("⬅️ Volver al menú", callback_data='menu')],
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
        return data
    return {
        "registros": [], "chat_id": None, "flow": None, "esperando": None,
        "gastos": [], "habitos": [], "habito_flow": None,
        "ai_history": [], "ai_last_message": None, "pending_action": None,
        "trades": [], "notas": [], "trade_pending": None, "trade_fotos": [],
    }

def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_chat_id():
    return load_data().get("chat_id")

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
# SOFÍA — MODO PSICÓLOGA
# ------------------------------------

def get_sofia_mode() -> bool:
    return load_data().get("sofia_mode", False)

def set_sofia_mode(active: bool):
    data = load_data(); data["sofia_mode"] = active; save_data(data)

def get_sofia_history() -> list:
    data = load_data()
    history = data.get("sofia_history", [])
    last_time = data.get("sofia_last_message")
    if last_time:
        try:
            last_dt = datetime.fromisoformat(last_time)
            if last_dt.tzinfo is None:
                last_dt = TIMEZONE.localize(last_dt)
            if (datetime.now(TIMEZONE) - last_dt).total_seconds() > 8 * 3600:
                return []
        except Exception:
            pass
    return history[-20:]

def save_sofia_history(history: list, user_msg: str, assistant_msg: str):
    data = load_data()
    full = history + [
        {"role": "user",      "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    data["sofia_history"] = full[-40:]
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

    return (
        "📊 *RAÚL — RESUMEN DE LA SEMANA*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💪 *Hábitos \\(últimos 7 días\\)*\n{habitos_lines}"
        f"{trades_lines}\n"
        f"💰 *Gastos de la semana*\n{gastos_lines}"
        f"Total: ${total_g:.0f}\n\n"
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

# ------------------------------------
# IA — GROQ CHAT
# ------------------------------------

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

    return f"""Eres el asistente personal de Raúl, integrado en su bot de Telegram de vida organizada.

PERFIL DE RAÚL:
- Trader activo, usa estrategia Mark Jeffrey
- Testigo de Jehová, comprometido con su fe
- Vive con su abuelo, lo cuida
- Renta mensual fija: $8,000 pesos
- TikToker y creador de contenido
- Novia: Nallelita
- Trabaja activamente en disciplinarse: hábitos, dinero y trading

CONTEXTO ACTUAL ({now.strftime('%d/%m/%Y %H:%M')} Ciudad de México):
- Semanas de retroalimentación completadas: {num_semanas}
- Gastos este mes por categoría: {json.dumps(gastos_por_cat, ensure_ascii=False) if gastos_por_cat else 'ninguno'}
- Últimos gastos individuales:
{gastos_str}
- Hábitos últimos 7 días:
  gym: {habitos_resumen.get('gym','sin datos')}
  comida en casa: {habitos_resumen.get('comida_casa','sin datos')}
  trading según plan: {habitos_resumen.get('trading_plan','sin datos')}
- Trade abierto: {open_str}
- Trades recientes:
{trades_str}
- Notas guardadas:
{notas_str}
- Agenda próximas 48h:
{get_calendar_context()}

INSTRUCCIONES:
- Habla de tú a Raúl, en español mexicano, informal pero directo y con carácter
- Eres SU asistente personal — conoces su vida, sus metas, sus puntos débiles
- Respuestas cortas (máximo 3-4 líneas). Sin markdown (sin asteriscos, guiones bajos, etc.)
- Usa los datos reales del contexto para responder preguntas específicas
- Si pregunta sobre su agenda, usa los datos de calendario del contexto
- Conéctate con lo que sabes de él: trading, fe, abuelo, Nallelita, disciplina
- NUNCA corrijas ni cuestiones lo que Raúl dice de su propia vida, familia o situación personal. Él sabe mejor que tú. Si menciona a su padre, primo, amigo u otra persona, acéptalo y ayúdalo sin comentarios.

DETECCIÓN DE ACCIONES — incluye al final de tu respuesta (línea separada) si aplica:

Si detectas un gasto claro con monto:
ACCION_GASTO:[monto]:[categoria]
Categorías: comida, transporte, capricho, salud, otros

Si quiere guardar una nota/recordatorio:
ACCION_NOTA:[texto]

Si quiere VER su agenda (hoy, mañana, semana, etc):
ACCION_CAL_VER:[dias]
Ejemplo: ACCION_CAL_VER:1 (hoy), ACCION_CAL_VER:2 (mañana), ACCION_CAL_VER:7 (semana)

Si quiere CREAR un evento en el calendario:
ACCION_CAL_CREAR:[titulo]|[YYYY-MM-DD]|[HH:MM]|[duracion_minutos]
Ejemplo: ACCION_CAL_CREAR:Dentista|2026-04-15|15:00|60

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
                    action = {"type": "gasto", "amount": float(parts[1].strip()), "category": parts[2].strip().lower()}
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
- Integras lo que Raúl va compartiendo a lo largo de la sesión

Fecha: {now.strftime('%A %d/%m/%Y %H:%M')} (Ciudad de México)"""


def _call_sofia_sync(user_message: str, history: list) -> str:
    messages = (
        [{"role": "system", "content": build_sofia_system_prompt()}]
        + history
        + [{"role": "user", "content": user_message}]
    )
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
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

    # 1. Esperando descripción de gasto Gmail
    d = load_data()
    awaiting = d.get("gmail_awaiting_desc")
    if awaiting:
        short_id = awaiting["short_id"]
        monto    = awaiting["monto"]
        comercio = awaiting.get("comercio", "")
        desc     = text.strip()

        # Guardar gasto con descripción libre
        registrar_gasto(monto, None, descripcion=desc, comercio=comercio)

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

    # 2. Esperando respuesta de capital
    if get_esperando() == 'capital':
        guardar_registro('capital', text)
        fecha = escape_md(datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M"))
        await update.message.reply_text(
            f"✅ *División de capital guardada\\.*\n\n_{frase_aleatoria()}_\n\n⏰ _{fecha}_",
            parse_mode='MarkdownV2', reply_markup=menu_keyboard()
        )
        return

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
        "Escríbeme directamente o usa el menú\\.\n\n"
        "• Para gastos rápidos: `gasto 150 comida`\n"
        "• Para trades: manda cualquier foto y se guarda automáticamente\n"
        "• Para tickets: manda foto con caption `ticket` o `gasto`\n\n"
        "/capital \\— División de capital\n"
        "/gastos \\— Resumen gastos del mes\n"
        "/como\\_voy \\— Snapshot general\n"
        "/trades \\— Historial de trades\n"
        "/fotos\\_trades \\— Ver fotos de trades por fecha\n"
        "/notas \\— Ver notas guardadas\n"
        "/historial \\— Ver registros\n"
        "/cancelar \\— Cancelar flujo activo",
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
    set_esperando('capital')
    await update.message.reply_text(CAPITAL, parse_mode='MarkdownV2')

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_esperando('capital')
    await update.message.reply_text(CAPITAL, parse_mode='MarkdownV2')

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

    if data == 'capital':
        set_esperando('capital')
        await query.message.reply_text(CAPITAL, parse_mode='MarkdownV2')

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

    elif data == 'gastos':
        await query.message.reply_text(generar_resumen_gastos(), parse_mode='MarkdownV2', reply_markup=menu_keyboard())

    elif data == 'como_voy':
        await query.message.reply_text(generar_como_voy(), parse_mode='MarkdownV2', reply_markup=menu_keyboard())

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

    elif data == 'menu':
        await query.message.reply_text("📋 *¿Qué quieres hacer?*", parse_mode='MarkdownV2', reply_markup=menu_keyboard())

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
            registrar_movimiento(monto, comercio or tx.get("descripcion", "movimiento"))
            pending.pop(short_id, None)
            d["gmail_pending"] = pending
            save_data(d)
            await query.message.edit_text(
                f"🔄 *Movimiento registrado*\n_{escape_md(f'${monto:,.2f}')} entre cuentas_",
                parse_mode='MarkdownV2'
            )

        elif tipo == "ingreso":
            registrar_ingreso(monto, "ingreso", comercio or tx.get("descripcion", ""))
            pending.pop(short_id, None)
            d["gmail_pending"] = pending
            save_data(d)
            await query.message.edit_text(
                f"💰 *Ingreso registrado*\n_{escape_md(f'${monto:,.2f}')}_",
                parse_mode='MarkdownV2'
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
        # Nivel 2 Gmail: tipo de ingreso
        parts = data.split(':', 2)
        if len(parts) < 3:
            return
        short_id    = parts[1]
        tipo_ingreso = parts[2]

        d = load_data()
        pending = d.get("gmail_pending", {})
        tx = pending.get(short_id)
        if not tx:
            await query.answer("Ya procesado.")
            return

        monto = tx.get("monto", 0)
        registrar_ingreso(monto, tipo_ingreso, tx.get("comercio", "") or tx.get("descripcion", ""))
        pending.pop(short_id, None)
        d["gmail_pending"] = pending
        save_data(d)

        tipos_label = {"renta": "Renta", "transferencia": "Transferencia recibida",
                       "rendimientos": "Rendimientos", "otro": "Otro ingreso"}
        label = escape_md(tipos_label.get(tipo_ingreso, tipo_ingreso.capitalize()))
        await query.message.edit_text(
            f"💰 *Ingreso registrado*\n_{escape_md(f'${monto:,.2f}')} — {label}_",
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

        registrar_gasto(monto, categoria, comercio=comercio)
        pending.pop(short_id, None)
        d["gmail_pending"] = pending
        save_data(d)
        cat_esc   = escape_md(categoria.capitalize())
        monto_esc = escape_md(f"${monto:,.2f}")
        await query.message.edit_text(
            f"✅ *{monto_esc} en {cat_esc} registrado*",
            parse_mode='MarkdownV2'
        )

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
            set_esperando('capital')
            await context.bot.send_message(chat_id, CAPITAL, parse_mode='MarkdownV2')

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


def _parse_email_financial_sync(subject: str, from_addr: str, body: str) -> dict | None:
    """
    Usa Groq para decidir si el email es financiero y extraer datos.
    Retorna dict con {tipo, monto, comercio, descripcion} o None si no es financiero.
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
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
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
        return result if "monto" in result else None
    except Exception as e:
        logger.error(f"Gmail AI parse error: {e}")
        return None


def _fetch_gmail_transactions_sync(refresh_token: str, last_history_id: str | None, window_hours: int = 1) -> list[dict]:
    """Busca emails financieros nuevos. Retorna lista de transacciones detectadas."""
    service = _get_gmail_service(refresh_token)
    if not service:
        return []

    import time as time_mod
    since = int(time_mod.time()) - window_hours * 3600
    # Convertir a formato fecha para Gmail (más compatible que Unix timestamp)
    from datetime import datetime as _dt
    since_date = _dt.utcfromtimestamp(since).strftime('%Y/%m/%d')
    logger.info(f"Gmail search: últimas {window_hours}h (desde {since_date})")
    # Buscar todos los emails recientes — la IA filtra cuáles son financieros
    query = f"after:{since_date}"
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
# FOREX FACTORY — NOTICIAS ALTO IMPACTO
# ------------------------------------

def _fetch_forex_news_sync(target_date=None):
    """Descarga eventos de alto impacto de ForexFactory para una fecha dada."""
    import urllib.request
    import xml.etree.ElementTree as ET

    et_tz = pytz.timezone('America/New_York')  # ForexFactory usa ET
    mx_tz = TIMEZONE

    if target_date is None:
        target_date = datetime.now(mx_tz).date()

    # Intentar semana actual y siguiente
    urls = [
        "https://www.forexfactory.com/ffcal_week_this.xml",
        "https://www.forexfactory.com/ffcal_week_next.xml",
    ]

    all_events = []
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
        except Exception as e:
            logger.warning(f"ForexFactory fetch error ({url}): {e}")
            continue

        for ev in root.findall('event'):
            impact = ev.findtext('impact', '').strip().lower()
            if impact != 'high':
                continue

            title    = ev.findtext('title', '').strip()
            country  = ev.findtext('country', '').strip()
            date_str = ev.findtext('date', '').strip()
            time_str = ev.findtext('time', '').strip()
            forecast = ev.findtext('forecast', '').strip()
            previous = ev.findtext('previous', '').strip()

            try:
                # Formato: "Sunday, Apr 13, 2026"  hora: "8:30am"
                if time_str.lower() in ('all day', 'tentative', ''):
                    # Parsear solo la fecha
                    date_obj = datetime.strptime(date_str, "%A, %b %d, %Y").date()
                    if date_obj != target_date:
                        continue
                    hora_mx  = "Todo el día"
                    sort_key = 0
                else:
                    dt_str  = f"{date_str} {time_str.upper()}"
                    dt_et   = datetime.strptime(dt_str, "%A, %b %d, %Y %I:%M%p")
                    dt_et   = et_tz.localize(dt_et)
                    dt_mx   = dt_et.astimezone(mx_tz)
                    if dt_mx.date() != target_date:
                        continue
                    hora_mx  = dt_mx.strftime("%H:%M")
                    sort_key = dt_mx.hour * 60 + dt_mx.minute
            except Exception as e:
                logger.warning(f"FF parse error '{date_str} {time_str}': {e}")
                continue

            all_events.append({
                'title':    title,
                'country':  country,
                'hora_mx':  hora_mx,
                'forecast': forecast,
                'previous': previous,
                'sort_key': sort_key,
            })

    all_events.sort(key=lambda x: x['sort_key'])
    return all_events


def _format_forex_news(events, fecha_label="hoy"):
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


async def cmd_noticias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra noticias de alto impacto del día (o mañana con /noticias mañana)."""
    arg = " ".join(context.args).strip().lower() if context.args else ""
    mx  = TIMEZONE
    now = datetime.now(mx)

    if arg in ("mañana", "manana", "tomorrow"):
        target = (now + timedelta(days=1)).date()
        label  = "mañana"
    else:
        target = now.date()
        label  = f"{now.strftime('%A %d/%m')}"

    msg = await update.message.reply_text("🔍 Consultando ForexFactory...")
    try:
        events = await asyncio.wait_for(
            asyncio.to_thread(_fetch_forex_news_sync, target),
            timeout=20
        )
        texto = _format_forex_news(events, label)
        await update.message.reply_text(texto)
    except asyncio.TimeoutError:
        await msg.edit_text("⏱ ForexFactory tardó demasiado. Intenta de nuevo.")
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
        events = await asyncio.to_thread(_fetch_forex_news_sync, target)
        msg    = _format_forex_news(events, label)
        await context.bot.send_message(chat_id=chat_id, text=msg)
    except Exception as e:
        logger.error(f"job_forex_news error: {e}")


async def job_gmail_check(context: ContextTypes.DEFAULT_TYPE, window_hours: float = 0.05):
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
    app.add_handler(CommandHandler("test",      cmd_test))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    jq = app.job_queue
    mx = TIMEZONE
    jq.run_daily(job_semanal,        time=dt_time(21, 10, tzinfo=mx), days=(3,), name="semanal")
    jq.run_daily(job_mensual,        time=dt_time(8,  0,  tzinfo=mx), days=(4,), name="mensual")
    jq.run_daily(job_capital,        time=dt_time(8,  0,  tzinfo=mx),            name="capital")
    jq.run_daily(job_enviar_informe, time=dt_time(8,  0,  tzinfo=mx),            name="enviar_informe")
    jq.run_daily(job_pedir_informe,  time=dt_time(20, 30, tzinfo=mx),            name="pedir_informe")
    jq.run_daily(job_habitos,        time=dt_time(21, 0,  tzinfo=mx),            name="habitos")
    jq.run_daily(job_forex_news,     time=dt_time(6,  0,  tzinfo=mx),            name="forex_news")
    # Gmail: revisar cada 30 minutos si las credenciales están configuradas
    if os.environ.get("GMAIL_CLIENT_ID"):
        jq.run_repeating(job_gmail_check, interval=60, first=30, name="gmail")

    logger.info("Bot iniciado. Esperando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
