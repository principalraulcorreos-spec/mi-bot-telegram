# -*- coding: utf-8 -*-
"""
Configuracion y datos personalizables del bot.
EDITA ESTE ARCHIVO para adaptar el bot a tu propia vida: presupuesto,
categorias de gasto, habitos, rutina, frases motivacionales, preguntas de
reflexion, etc. El resto del proyecto no deberia necesitar cambios.
"""
import os
import re

import pytz


TOKEN      = os.environ["BOT_TOKEN"]


TIMEZONE   = pytz.timezone('America/Mexico_City')


DATA_DIR   = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))


DATA_FILE  = os.path.join(DATA_DIR, "registro.json")


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")


SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)


SUPABASE_TABLE_URL = f"{SUPABASE_URL}/rest/v1/bot_data" if SUPABASE_ENABLED else None


PENDING_ACTION_TTL_SECONDS = 15 * 60


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


HABITOS = [
    ("gym",          "💪 ¿Hiciste gym hoy?"),
    ("comida_casa",  "🍽 ¿Comiste en casa según lo planeado?"),
    ("trading_plan", "📈 ¿Respetaste tu estrategia de trading hoy?"),
    ("templanza",    "🧠 ¿Lograste no masturbarte hoy?"),
]


EMOCIONES_TRADE = [
    ("plan",       "✅ Según el plan"),
    ("miedo",      "😰 Salí por miedo"),
    ("impaciente", "😤 Cerré antes"),
    ("sl",         "🔴 Stop loss"),
]


RUTINA_LMV = [
    ("Calentamiento",    "10-15 min cardio suave (caminata/bici)"),
    ("Pecho & Triceps",  "Press plano 4x10 | Fondos 3x12 | Extensiones 3x15"),
    ("Espalda & Biceps", "Jalones 4x10 | Remo 3x12 | Curl 3x15"),
    ("Pierna",           "Sentadilla 4x10 | Prensa 3x12 | Extensiones 3x15"),
    ("Core",             "Plancha 3x45s | Abdominales 3x20"),
    ("Enfriamiento",     "10 min stretching completo"),
]


CORTE_CABELLO_BASE = "2026-04-25"


META_PASOS_DIARIO = 8000


META_CAL_BASE     = 2000  # se actualiza automático con el peso


def _calcular_meta_calorias(peso_kg: float) -> int:
    """Mifflin-St Jeor para hombre activo (actividad moderada)."""
    # Asume: hombre, 25 años, 175 cm, actividad moderada (x1.55)
    tmb = 10 * peso_kg + 6.25 * 175 - 5 * 25 + 5
    return round(tmb * 1.55)


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

