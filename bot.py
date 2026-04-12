# -*- coding: utf-8 -*-
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

TOKEN = os.environ["BOT_TOKEN"]
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
TIMEZONE = pytz.timezone('America/Mexico_City')
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(DATA_DIR, "registro.json")

# ------------------------------------
# UTILIDADES (primero para que todo lo use)
# ------------------------------------

def escape_md(text):
    chars = r'_*[]()~`>#+-=|{}.!'
    for c in chars:
        text = text.replace(c, f'\\{c}')
    return str(text)

# ------------------------------------
# PRESUPUESTO MENSUAL (pesos)
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
# HÁBITOS DIARIOS
# ------------------------------------

HABITOS = [
    ("gym",          "💪 ¿Hiciste gym hoy?"),
    ("comida_casa",  "🍽 ¿Comiste en casa según lo planeado?"),
    ("trading_plan", "📈 ¿Respetaste tu estrategia de trading hoy?"),
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
# PREGUNTAS SEMANAL (una por una)
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
# PREGUNTAS MENSUAL (una por una)
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
            InlineKeyboardButton("📚 Historial", callback_data='historial'),
        ],
        [
            InlineKeyboardButton("💸 Gastos del Mes", callback_data='gastos'),
            InlineKeyboardButton("🎯 ¿Cómo voy?", callback_data='como_voy'),
        ],
    ])

def historial_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Semanales", callback_data='hist_semanal'),
            InlineKeyboardButton("🧠 Mensuales", callback_data='hist_mensual'),
        ],
        [
            InlineKeyboardButton("💰 Capital", callback_data='hist_capital'),
            InlineKeyboardButton("📋 Todo", callback_data='hist_todo'),
        ],
        [
            InlineKeyboardButton("⬅️ Volver al menú", callback_data='menu'),
        ]
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
            InlineKeyboardButton("❌ No", callback_data='accion_no'),
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
        return data
    return {
        "registros": [], "chat_id": None, "flow": None, "esperando": None,
        "gastos": [], "habitos": [], "habito_flow": None,
        "ai_history": [], "ai_last_message": None, "pending_action": None,
    }

def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"save_data: flow={data.get('flow')}, esperando={data.get('esperando')}")

def get_chat_id():
    return load_data().get("chat_id")

def set_chat_id(chat_id):
    data = load_data()
    data["chat_id"] = chat_id
    save_data(data)

def get_flow():
    return load_data().get("flow")

def set_flow(tipo, paso, respuestas):
    data = load_data()
    data["flow"] = {"tipo": tipo, "paso": paso, "respuestas": respuestas}
    save_data(data)

def get_esperando():
    return load_data().get("esperando")

def set_esperando(tipo):
    data = load_data()
    data["esperando"] = tipo
    save_data(data)

def guardar_registro(tipo, respuesta):
    data = load_data()
    data["registros"].append({
        "tipo": tipo,
        "fecha": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "respuesta": respuesta
    })
    data["flow"] = None
    data["esperando"] = None
    save_data(data)

def registrar_gasto(cantidad, categoria):
    cat = CATEGORIAS_ALIAS.get(categoria.lower(), categoria.lower())
    data = load_data()
    data["gastos"].append({
        "fecha": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "cantidad": float(cantidad),
        "categoria": cat,
    })
    save_data(data)
    return cat

def get_gastos_mes(año=None, mes=None):
    now = datetime.now(TIMEZONE)
    año = año or now.year
    mes = mes or now.month
    data = load_data()
    return [
        g for g in data.get("gastos", [])
        if g["fecha"].startswith(f"{año:04d}-{mes:02d}")
    ]

def get_habitos_dias(n=7):
    now = datetime.now(TIMEZONE).date()
    cutoff = now - timedelta(days=n - 1)
    data = load_data()
    return [
        h for h in data.get("habitos", [])
        if datetime.strptime(h["fecha"], "%Y-%m-%d").date() >= cutoff
    ]

def set_habito_flow(paso, respuestas):
    data = load_data()
    data["habito_flow"] = {"paso": paso, "respuestas": respuestas}
    save_data(data)

def registrar_habito(respuestas):
    data = load_data()
    data["habitos"].append({
        "fecha": datetime.now(TIMEZONE).strftime("%Y-%m-%d"),
        "respuestas": respuestas,
    })
    data["habito_flow"] = None
    save_data(data)

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
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    data["ai_history"] = full[-20:]
    data["ai_last_message"] = datetime.now(TIMEZONE).isoformat()
    save_data(data)

def set_pending_action(action):
    data = load_data()
    data["pending_action"] = action
    save_data(data)

def get_pending_action():
    return load_data().get("pending_action")

def clear_pending_action():
    data = load_data()
    data["pending_action"] = None
    save_data(data)

def clear_all_flows():
    data = load_data()
    data["flow"] = None
    data["esperando"] = None
    data["habito_flow"] = None
    data["pending_action"] = None
    save_data(data)

# ------------------------------------
# UTILIDADES (helpers)
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
    progreso = f"Pregunta {paso + 1} de {total}"
    tipo_label = "RETROALIMENTACIÓN SEMANAL" if tipo == 'semanal' else "REFLEXIÓN MENSUAL"
    texto = (
        f"⚡ *{escape_md(tipo_label)}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"_{escape_md(progreso)}_\n\n"
        f"*{escape_md(titulo)}*\n\n"
        f"{escape_md(pregunta)}\n\n"
        f"_Responde con calma\\. Estoy escuchando\\._ 👇"
    )
    await bot.send_message(chat_id, texto, parse_mode='MarkdownV2')

# ------------------------------------
# RESÚMENES (para /como_voy, resumen semanal, /gastos)
# ------------------------------------

def generar_resumen_semanal():
    habitos_7 = get_habitos_dias(7)
    now = datetime.now(TIMEZONE)
    cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    data = load_data()
    gastos_7 = [g for g in data.get("gastos", []) if g["fecha"][:10] >= cutoff]

    habitos_lines = ""
    for clave, label in HABITOS:
        short = label.split("¿")[-1].rstrip("?").strip() if "¿" in label else label
        if habitos_7:
            cumplidos = sum(1 for h in habitos_7 if h["respuestas"].get(clave))
            total = len(habitos_7)
            icons = "".join("✅" if h["respuestas"].get(clave) else "❌" for h in habitos_7[-7:])
            habitos_lines += f"\\- {escape_md(short)}: {icons} {cumplidos}/{total}\n"
        else:
            habitos_lines += f"\\- {escape_md(short)}: _sin datos_\n"

    gastos_por_cat = {}
    for g in gastos_7:
        gastos_por_cat[g["categoria"]] = gastos_por_cat.get(g["categoria"], 0) + g["cantidad"]
    total_gasto_semana = sum(gastos_por_cat.values())

    gastos_lines = ""
    for cat, total in sorted(gastos_por_cat.items(), key=lambda x: -x[1]):
        gastos_lines += f"\\- {escape_md(cat.capitalize())}: ${total:.0f}\n"
    if not gastos_lines:
        gastos_lines = "_Sin gastos registrados esta semana_\n"

    return (
        "📊 *RAÚL — RESUMEN DE LA SEMANA*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💪 *Hábitos \\(últimos 7 días\\)*\n{habitos_lines}\n"
        f"💰 *Gastos de la semana*\n{gastos_lines}"
        f"Total: ${total_gasto_semana:.0f}\n\n"
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
        presup = PRESUPUESTO.get(cat)
        cat_esc = escape_md(cat.capitalize())
        if presup:
            pct = gastado / presup * 100
            status = " ⚠️" if gastado > presup else ""
            lines += f"\\- *{cat_esc}*: ${gastado:.0f} / ${presup}{escape_md(status)} \\({pct:.0f}%\\)\n"
        else:
            lines += f"\\- *{cat_esc}*: ${gastado:.0f}\n"

    total_presup = sum(PRESUPUESTO.values())
    return (
        f"💸 *GASTOS — {mes_esc}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{lines}\n"
        f"*Total: ${total_gastado:.0f} / ${total_presup}*"
    )

def generar_como_voy():
    now = datetime.now(TIMEZONE)
    data = load_data()
    num_semanas = len([r for r in data.get("registros", []) if r["tipo"] == "semanal"])
    habitos_7 = get_habitos_dias(7)

    habitos_lines = ""
    for clave, label in HABITOS:
        short = label.split("¿")[-1].rstrip("?").strip() if "¿" in label else label
        if habitos_7:
            cumplidos = sum(1 for h in habitos_7 if h["respuestas"].get(clave))
            total_dias = len(habitos_7)
            icons = "".join("✅" if h["respuestas"].get(clave) else "❌" for h in habitos_7)
            habitos_lines += f"\\- {escape_md(short)}: {icons} {cumplidos}/{total_dias}\n"
        else:
            habitos_lines += f"\\- {escape_md(short)}: _sin datos_\n"

    gastos_mes = get_gastos_mes()
    total_gastado = sum(g["cantidad"] for g in gastos_mes)
    gastos_por_cat = {}
    for g in gastos_mes:
        gastos_por_cat[g["categoria"]] = gastos_por_cat.get(g["categoria"], 0) + g["cantidad"]

    gastos_lines = ""
    for cat in sorted(gastos_por_cat, key=lambda c: -gastos_por_cat[c]):
        gastado = gastos_por_cat[cat]
        presup = PRESUPUESTO.get(cat)
        cat_esc = escape_md(cat.capitalize())
        if presup:
            pct = gastado / presup * 100
            status = " ⚠️" if gastado > presup else ""
            gastos_lines += f"  \\- {cat_esc}: ${gastado:.0f}{escape_md(status)} \\({pct:.0f}%\\)\n"
        else:
            gastos_lines += f"  \\- {cat_esc}: ${gastado:.0f}\n"
    if not gastos_lines:
        gastos_lines = "  _Sin gastos este mes_\n"

    mes_esc = escape_md(now.strftime('%B').capitalize())
    total_presup = sum(PRESUPUESTO.values())
    return (
        f"🎯 *RAÚL — ¿CÓMO VAS?*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 *Semanas registradas:* {num_semanas}\n\n"
        f"💪 *Hábitos \\(últimos 7 días\\)*\n{habitos_lines}\n"
        f"💸 *Gastos de {mes_esc}*\n{gastos_lines}\n"
        f"*Total gastado: ${total_gastado:.0f} / ${total_presup}*"
    )

def mostrar_registros(registros, titulo):
    if not registros:
        return f"📚 *{escape_md(titulo)}*\n\n_Sin registros aún\\._"
    texto = f"📚 *{escape_md(titulo)}*\n\n"
    for r in reversed(registros[-5:]):
        fecha = escape_md(r['fecha'])
        resp = escape_md(r['respuesta'][:300])
        texto += f"📅 _{fecha}_\n{resp}\n\n"
    return texto

# ------------------------------------
# IA — CLAUDE
# ------------------------------------

def build_system_prompt():
    now = datetime.now(TIMEZONE)
    gastos_mes = get_gastos_mes()
    habitos_7 = get_habitos_dias(7)
    data = load_data()
    num_semanas = len([r for r in data.get("registros", []) if r["tipo"] == "semanal"])

    gastos_por_cat = {}
    for g in gastos_mes:
        gastos_por_cat[g["categoria"]] = gastos_por_cat.get(g["categoria"], 0) + g["cantidad"]
    total_gastado = sum(gastos_por_cat.values())

    habitos_resumen = {}
    for clave, _ in HABITOS:
        if habitos_7:
            cumplidos = sum(1 for h in habitos_7 if h["respuestas"].get(clave))
            habitos_resumen[clave] = f"{cumplidos}/{len(habitos_7)}"
        else:
            habitos_resumen[clave] = "sin datos"

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
- Gastos este mes: ${total_gastado:.0f} de ${sum(PRESUPUESTO.values())} presupuesto
- Detalle gastos mes: {json.dumps(gastos_por_cat, ensure_ascii=False) if gastos_por_cat else 'ninguno aún'}
- Hábitos últimos 7 días — gym: {habitos_resumen.get('gym', 'sin datos')}, comida en casa: {habitos_resumen.get('comida_casa', 'sin datos')}, trading según plan: {habitos_resumen.get('trading_plan', 'sin datos')}

INSTRUCCIONES:
- Habla de tú a Raúl, en español mexicano, informal pero directo y con carácter
- Eres SU asistente personal — conoces su vida, sus metas, sus puntos débiles
- Respuestas cortas (máximo 3-4 líneas). Sin emojis excesivos.
- Conéctate con lo que ya sabes de él: trading, fe, abuelo, Nallelita, disciplina
- Nunca uses markdown en tus respuestas (sin asteriscos, guiones bajos, etc.)
- Si menciona algo relevante de su vida, relaciónalo con sus metas

DETECCIÓN DE GASTOS:
Si en el mensaje detectas un gasto con monto numérico y categoría claros, agrega al final de tu respuesta (en línea separada):
ACCION_GASTO:[monto]:[categoria]
Ejemplo: ACCION_GASTO:150:comida
Categorías válidas: comida, transporte, capricho, ropa, salud, otros
Solo incluye esta línea si estás seguro del monto y categoría. Si el monto es ambiguo, no la incluyas."""

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
    lines = text.strip().split('\n')
    action = None
    clean_lines = []
    for line in lines:
        if line.startswith('ACCION_GASTO:'):
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    amount = float(parts[1].strip())
                    category = parts[2].strip().lower()
                    action = {"type": "gasto", "amount": amount, "category": category}
                except Exception:
                    pass
        else:
            clean_lines.append(line)
    return '\n'.join(clean_lines).strip(), action

async def handle_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    history = get_ai_history()
    raw_response = await call_ai(text, history)
    message_text, action = parse_ai_response(raw_response)
    save_ai_history(history, text, raw_response)

    if action and action["type"] == "gasto":
        set_pending_action(action)
        cat_cap = action['category'].capitalize()
        await update.message.reply_text(
            f"{message_text}\n\n💸 ¿Registro ${action['amount']:.0f} en {cat_cap}?",
            reply_markup=confirm_keyboard()
        )
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
        tg_file = await context.bot.get_file(voice.file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        text = await asyncio.to_thread(_transcribe_sync, audio_bytes)
        logger.info(f"Audio transcrito: {text}")
        await update.message.reply_text(
            f"🎙 _{escape_md(text)}_",
            parse_mode='MarkdownV2'
        )
        await process_text_message(update, context, text)
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        await update.message.reply_text("No pude entender el audio. Intenta de nuevo.")

# ------------------------------------
# PROCESAMIENTO CENTRAL DE TEXTO
# ------------------------------------

async def process_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    # 1. Flujo semanal/mensual activo
    flow = get_flow()
    if flow:
        tipo = flow['tipo']
        paso = flow['paso']
        respuestas = flow.get('respuestas', [])
        preguntas = PREGUNTAS_SEMANAL if tipo == 'semanal' else PREGUNTAS_MENSUAL
        titulo, _ = preguntas[paso]
        respuestas.append(f"{titulo}: {text}")
        siguiente = paso + 1
        if siguiente < len(preguntas):
            set_flow(tipo, siguiente, respuestas)
            await enviar_pregunta(context.bot, update.effective_chat.id, tipo, siguiente)
        else:
            respuesta_completa = "\n\n".join(respuestas)
            guardar_registro(tipo, respuesta_completa)
            fecha = escape_md(datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M"))
            base = "✅ *Retroalimentación semanal completa\\.* 💪" if tipo == 'semanal' else "✅ *Reflexión mensual completa\\.* 🧠"
            frase = frase_aleatoria()
            await update.message.reply_text(
                f"{base}\n\n_{frase}_\n\n⏰ _{fecha}_",
                parse_mode='MarkdownV2',
                reply_markup=menu_keyboard()
            )
        return

    # 2. Esperando respuesta de capital
    if get_esperando() == 'capital':
        guardar_registro('capital', text)
        fecha = escape_md(datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M"))
        frase = frase_aleatoria()
        await update.message.reply_text(
            f"✅ *División de capital guardada\\.*\n\n_{frase}_\n\n⏰ _{fecha}_",
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )
        return

    # 3. Patrón rápido de gasto: "gasto 150 comida"
    m = GASTO_RE.match(text.strip())
    if m:
        cantidad = float(m.group(1))
        cat_raw = m.group(2).lower()
        cat = registrar_gasto(cantidad, cat_raw)
        gastos_mes = get_gastos_mes()
        total_cat = sum(g["cantidad"] for g in gastos_mes if g["categoria"] == cat)
        presup = PRESUPUESTO.get(cat)
        cat_esc = escape_md(cat.capitalize())
        if presup:
            pct = total_cat / presup * 100
            alert = " ⚠️ ¡Superado\\!" if total_cat > presup else f" \\({pct:.0f}% del mes\\)"
        else:
            alert = ""
        await update.message.reply_text(
            f"✅ *${cantidad:.0f} en {cat_esc} registrado*\n_{cat_esc} este mes: ${total_cat:.0f}{alert}_",
            parse_mode='MarkdownV2'
        )
        return

    # 4. IA — catch-all para mensajes libres
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
        "Puedes escribirme directamente o usar el menú\\.\n\n"
        "Para registrar un gasto: `gasto 150 comida`\n\n"
        "/capital \\— División de capital\n"
        "/gastos \\— Resumen gastos del mes\n"
        "/como\\_voy \\— Snapshot general\n"
        "/historial \\— Ver registros\n"
        "/cancelar \\— Cancelar flujo activo",
        parse_mode='MarkdownV2',
        reply_markup=menu_keyboard()
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *¿Qué quieres hacer?*",
        parse_mode='MarkdownV2',
        reply_markup=menu_keyboard()
    )

async def cmd_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    set_flow('semanal', 0, [])
    await enviar_pregunta(context.bot, update.effective_chat.id, 'semanal', 0)

async def cmd_mensual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    set_flow('mensual', 0, [])
    await enviar_pregunta(context.bot, update.effective_chat.id, 'mensual', 0)

async def cmd_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_esperando('capital')
    await update.message.reply_text(CAPITAL, parse_mode='MarkdownV2')

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_esperando('capital')
    await update.message.reply_text(CAPITAL, parse_mode='MarkdownV2')

async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_all_flows()
    await update.message.reply_text(
        "✅ Flujo cancelado\\.",
        parse_mode='MarkdownV2',
        reply_markup=menu_keyboard()
    )

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Historial — ¿Qué categoría?*",
        parse_mode='MarkdownV2',
        reply_markup=historial_keyboard()
    )

async def cmd_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        generar_resumen_gastos(),
        parse_mode='MarkdownV2',
        reply_markup=menu_keyboard()
    )

async def cmd_como_voy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        generar_como_voy(),
        parse_mode='MarkdownV2',
        reply_markup=menu_keyboard()
    )

# ------------------------------------
# CALLBACK DE BOTONES
# ------------------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'reporte':
        set_chat_id(query.message.chat_id)
        set_flow('semanal', 0, [])
        await enviar_pregunta(context.bot, query.message.chat_id, 'semanal', 0)

    elif data == 'mensual':
        set_chat_id(query.message.chat_id)
        set_flow('mensual', 0, [])
        await enviar_pregunta(context.bot, query.message.chat_id, 'mensual', 0)

    elif data == 'capital':
        set_esperando('capital')
        await query.message.reply_text(CAPITAL, parse_mode='MarkdownV2')

    elif data == 'historial':
        await query.message.reply_text(
            "📚 *Historial — ¿Qué categoría?*",
            parse_mode='MarkdownV2',
            reply_markup=historial_keyboard()
        )

    elif data in ('hist_semanal', 'hist_mensual', 'hist_capital', 'hist_todo'):
        todos = load_data().get("registros", [])
        if data == 'hist_semanal':
            filtrados = [r for r in todos if r['tipo'] == 'semanal']
            titulo = "Reportes Semanales"
        elif data == 'hist_mensual':
            filtrados = [r for r in todos if r['tipo'] == 'mensual']
            titulo = "Reflexiones Mensuales"
        elif data == 'hist_capital':
            filtrados = [r for r in todos if r['tipo'] == 'capital']
            titulo = "Divisiones de Capital"
        else:
            filtrados = todos
            titulo = "Todos los registros"
        texto = mostrar_registros(filtrados, titulo)
        await query.message.reply_text(texto, parse_mode='MarkdownV2', reply_markup=historial_keyboard())

    elif data == 'gastos':
        await query.message.reply_text(
            generar_resumen_gastos(),
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )

    elif data == 'como_voy':
        await query.message.reply_text(
            generar_como_voy(),
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )

    elif data == 'menu':
        await query.message.reply_text(
            "📋 *¿Qué quieres hacer?*",
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )

    elif data in ('hab_si', 'hab_no'):
        d = load_data()
        hf = d.get("habito_flow")
        if not hf:
            await query.answer("No hay check-in activo.")
            return
        paso = hf["paso"]
        respuestas = hf["respuestas"]
        clave, pregunta_text = HABITOS[paso]
        respuesta_bool = (data == 'hab_si')
        respuestas[clave] = respuesta_bool

        resp_label = "Sí ✅" if respuesta_bool else "No ❌"
        short = pregunta_text.split("¿")[-1].rstrip("?").strip() if "¿" in pregunta_text else pregunta_text
        await query.message.edit_text(
            f"_{escape_md(short)}_: *{resp_label}*",
            parse_mode='MarkdownV2'
        )

        siguiente = paso + 1
        if siguiente < len(HABITOS):
            set_habito_flow(siguiente, respuestas)
            _, prox = HABITOS[siguiente]
            await query.message.reply_text(
                f"*{escape_md(prox)}*",
                parse_mode='MarkdownV2',
                reply_markup=habito_keyboard()
            )
        else:
            registrar_habito(respuestas)
            cumplidos = sum(1 for v in respuestas.values() if v)
            total = len(HABITOS)
            emoji = "🔥" if cumplidos == total else "💪" if cumplidos >= 2 else "😤"
            frase = frase_aleatoria()
            await query.message.reply_text(
                f"✅ *Hábitos del día guardados\\. {cumplidos}/{total} {emoji}*\n\n_{frase}_",
                parse_mode='MarkdownV2'
            )

    elif data == 'accion_si':
        action = get_pending_action()
        if not action:
            return
        clear_pending_action()
        if action["type"] == "gasto":
            cat = registrar_gasto(action["amount"], action["category"])
            gastos_mes = get_gastos_mes()
            total_cat = sum(g["cantidad"] for g in gastos_mes if g["categoria"] == cat)
            presup = PRESUPUESTO.get(cat)
            cat_esc = escape_md(cat.capitalize())
            if presup:
                pct = total_cat / presup * 100
                extra = f" \\({pct:.0f}% del mes\\)"
            else:
                extra = ""
            await query.message.reply_text(
                f"✅ *${action['amount']:.0f} en {cat_esc} registrado*\n_{cat_esc} este mes: ${total_cat:.0f}{extra}_",
                parse_mode='MarkdownV2'
            )

    elif data == 'accion_no':
        clear_pending_action()
        await query.answer("Ok, no se registró nada.")

# ------------------------------------
# HANDLER DE MENSAJES DE TEXTO
# ------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    await process_text_message(update, context, text)

# ------------------------------------
# JOBS PROGRAMADOS
# ------------------------------------

async def job_semanal(context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id()
    if not chat_id:
        return
    # Enviar resumen de la semana antes de las preguntas
    resumen = generar_resumen_semanal()
    await context.bot.send_message(chat_id, resumen, parse_mode='MarkdownV2')
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
    if not chat_id:
        return
    set_habito_flow(0, {})
    _, primera = HABITOS[0]
    await context.bot.send_message(
        chat_id,
        f"🌙 *RAÚL — CHECK\\-IN DIARIO*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"*{escape_md(primera)}*",
        parse_mode='MarkdownV2',
        reply_markup=habito_keyboard()
    )

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
    app.add_handler(CommandHandler("cancelar",  cmd_cancelar))
    app.add_handler(CommandHandler("test",      cmd_test))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    jq = app.job_queue
    mx = TIMEZONE

    jq.run_daily(job_semanal,        time=dt_time(21, 10, tzinfo=mx), days=(3,), name="semanal")
    jq.run_daily(job_mensual,        time=dt_time(8,  0,  tzinfo=mx), days=(4,), name="mensual")
    jq.run_daily(job_capital,        time=dt_time(8,  0,  tzinfo=mx),            name="capital")
    jq.run_daily(job_enviar_informe, time=dt_time(8,  0,  tzinfo=mx),            name="enviar_informe")
    jq.run_daily(job_pedir_informe,  time=dt_time(20, 30, tzinfo=mx),            name="pedir_informe")
    jq.run_daily(job_habitos,        time=dt_time(21, 0,  tzinfo=mx),            name="habitos")

    logger.info("Bot iniciado. Esperando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
