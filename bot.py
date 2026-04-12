# -*- coding: utf-8 -*-
import json
import logging
import os
from datetime import datetime, time as dt_time
from calendar import monthcalendar, FRIDAY

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ["BOT_TOKEN"]
TIMEZONE = pytz.timezone('America/Mexico_City')
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(DATA_DIR, "registro.json")

# ------------------------------------
# PREGUNTAS SEMANAL (una por una)
# ------------------------------------

PREGUNTAS_SEMANAL = [
    (
        "1\ufe0f\u20e3 EL PULSO DE LA SEMANA",
        "\u2022 Control vs Reacci\u00f3n: \u00bf80% control o te arrastr\u00f3 la semana?\n"
        "\u2022 Emoci\u00f3n dominante: \u00bfCalma o ansiedad?\n"
        "\u2022 \u00bfD\u00f3nde estuviste a punto de traicionarte?"
    ),
    (
        "2\ufe0f\u20e3 DINERO Y EL RA\u00daL DEL FUTURO",
        "\u2022 \u00bfQu\u00e9 % de tus gastos fueron fugas?\n"
        "\u2022 \u00bfLe robaste al Ra\u00fal del futuro? \u00bfCu\u00e1l fue el disparador?\n"
        "\u2022 \u00bfEn qu\u00e9 momento dijiste NO a un gasto impulsivo?"
    ),
    (
        "3\ufe0f\u20e3 SISTEMAS Y TRADING",
        "\u2022 Del 1 al 10, \u00bfcu\u00e1nto respetaste tu estrategia?\n"
        "\u2022 \u00bfCerraste trades por miedo o incomodidad?\n"
        "\u2022 \u00bfEsperaste tu configuraci\u00f3n o forzaste entradas?"
    ),
    (
        "4\ufe0f\u20e3 TEMPLANZA E IMPULSOS",
        "\u2022 \u00bfCediste a impulsos carnales o transmitiste esa energ\u00eda?\n"
        "\u2022 \u00bfComiste en casa seg\u00fan lo planeado?"
    ),
    (
        "5\ufe0f\u20e3 HUMILDAD Y CAR\u00c1CTER",
        "\u2022 \u00bfReconociste que a\u00fan est\u00e1s aprendiendo?\n"
        "\u2022 \u00bfAceptaste correcci\u00f3n o te defendiste por orgullo silencioso?"
    ),
    (
        "6\ufe0f\u20e3 RELACIONES Y PAZ",
        "\u2022 \u00bfFuiste un apoyo real para tu familia y amigos?\n"
        "\u2022 \u00bfHablaste desde la verdad o desde el c\u00e1lculo?"
    ),
    (
        "7\ufe0f\u20e3 CIERRE",
        "Calificaci\u00f3n de la semana (1-10): ___\n"
        "\u00bfQu\u00e9 UNA cosa har\u00e1s diferente el lunes?"
    ),
]

# ------------------------------------
# PREGUNTAS MENSUAL (una por una)
# ------------------------------------

PREGUNTAS_MENSUAL = [
    (
        "1\ufe0f\u20e3 ESTE MES, \u00bfC\u00d3MO VIVISTE?",
        "\u2022 \u00bfRespondiste a la vida o la dirigiste?\n"
        "\u2022 \u00bfQu\u00e9 emoci\u00f3n domin\u00f3 m\u00e1s tus d\u00edas?\n"
        "\u2022 \u00bfEn qu\u00e9 momentos te traicionaste?"
    ),
    (
        "2\ufe0f\u20e3 DINERO",
        "\u2022 \u00bfTu dinero te dio paz o estr\u00e9s este mes?\n"
        "\u2022 \u00bfGastaste con intenci\u00f3n o por impulso?\n"
        "\u2022 \u00bfQu\u00e9 decisi\u00f3n financiera repetir\u00edas? \u00bfCu\u00e1l no?"
    ),
    (
        "3\ufe0f\u20e3 DISCIPLINA Y H\u00c1BITOS",
        "\u2022 \u00bfQu\u00e9 h\u00e1bito peque\u00f1o s\u00ed cumpliste?\n"
        "\u2022 \u00bfD\u00f3nde te mentiste diciendo \"luego\"?\n"
        "\u2022 \u00bfQu\u00e9 h\u00e1bito sostenido 30 d\u00edas m\u00e1s te cambiar\u00eda el a\u00f1o?"
    ),
    (
        "4\ufe0f\u20e3 RELACIONES",
        "\u2022 \u00bfA qui\u00e9n cuidaste de verdad?\n"
        "\u2022 \u00bfFuiste refugio emocional o carga?"
    ),
    (
        "5\ufe0f\u20e3 FE / VIDA INTERIOR",
        "\u2022 \u00bfEste mes confiaste incluso sin entender?\n"
        "\u2022 \u00bfQu\u00e9 agradeces sinceramente?"
    ),
    (
        "6\ufe0f\u20e3 BALANCE MENSUAL",
        "Califica del 1 al 10: Orden / Paz / Avance / Honestidad / Humildad\n\n"
        "\"Este mes aprend\u00ed que ___.\"\n"
        "\"El pr\u00f3ximo mes me enfocar\u00e9 en ___.\""
    ),
]

# ------------------------------------
# MENSAJE CAPITAL (sigue siendo uno solo)
# ------------------------------------

CAPITAL = (
    "\U0001f4b0 *RA\u00daL \u2014 TU DINERO DEL MES ESPERA \u00d3RDENES*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f4b0 *DIVISI\u00d3N DE CAPITAL*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n\n"
    "Renta recibida: *$8,000 pesos*\n"
    "\\(\u2212400 mantenimiento \\= $7,600 disponibles\\)\n\n"
    "\u00bfCu\u00e1nto va a cada \u00e1rea?\n"
    "\u2022 \U0001f4b9 Trading / Inversi\u00f3n: $\\_\\_\\_\n"
    "\u2022 \U0001f37d Gastos del mes: $\\_\\_\\_\n"
    "\u2022 \U0001f3e6 Ahorro \\(CETES\\): $\\_\\_\\_\n"
    "\u2022 \U0001f527 Mantenimiento: $400 \\(fijo\\)\n\n"
    "*Total debe ser $8,000*\n\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f4dd *Define tu capital ahora mismo\\.* \U0001f447"
)

PEDIR_INFORME = (
    "\U0001f4f2 *RA\u00daL \u2014 PIDE LOS INFORMES HOY*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n\n"
    "\U0001f4f1 Manda este WhatsApp a los hermanos *ahora*:\n\n"
    "_\"Hermanos, ya es fin de mes\\. Por favor env\u00edenme su informe cuando puedan\\. Gracias\\.\"_\n\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\u26a0\ufe0f *No lo dejes para ma\u00f1ana\\.*"
)

ENVIAR_INFORME = (
    "\U0001f6a8 *RA\u00daL \u2014 HOY ES EL L\u00cdMITE\\. ENV\u00cdA EL INFORME*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n\n"
    "\u26a0\ufe0f Hoy es el d\u00eda 4\\. *L\u00edmite hoy\\.* \u26a0\ufe0f\n\n"
    "Recopila los informes recibidos y env\u00edalos\n"
    "a la persona correspondiente de la congregaci\u00f3n\\.\n\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f4e4 *H\u00e1zlo antes de las 12PM\\.* \u23f0"
)

# ------------------------------------
# CONFIRMACIONES
# ------------------------------------

CONFIRMACIONES = {
    'semanal': (
        "\u2705 *Retroalimentaci\u00f3n semanal completa\\.* \U0001f4aa\n\n"
        "_Lo que se mide, mejora\\. Esta semana ya qued\u00f3 registrada\\._\n"
        "_El lunes empieza desde aqu\u00ed\\._"
    ),
    'mensual': (
        "\u2705 *Reflexi\u00f3n mensual completa\\.* \U0001f9e0\n\n"
        "_Un mes m\u00e1s consciente es un a\u00f1o diferente\\._\n"
        "_Sigue siendo honesto contigo mismo\\._"
    ),
    'capital': (
        "\u2705 *Divisi\u00f3n de capital guardada\\.* \U0001f4b0\n\n"
        "_Decidir a d\u00f3nde va tu dinero antes de gastarlo_\n"
        "_es lo que separa al Ra\u00fal de hoy del Ra\u00fal del futuro\\._"
    ),
}

# ------------------------------------
# TECLADOS
# ------------------------------------

def menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f4ca Reporte Semanal", callback_data='reporte'),
            InlineKeyboardButton("\U0001f9e0 Reflexi\u00f3n Mensual", callback_data='mensual'),
        ],
        [
            InlineKeyboardButton("\U0001f4b0 Divisi\u00f3n de Capital", callback_data='capital'),
            InlineKeyboardButton("\U0001f4da Historial", callback_data='historial'),
        ]
    ])

def historial_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f4ca Semanales", callback_data='hist_semanal'),
            InlineKeyboardButton("\U0001f9e0 Mensuales", callback_data='hist_mensual'),
        ],
        [
            InlineKeyboardButton("\U0001f4b0 Capital", callback_data='hist_capital'),
            InlineKeyboardButton("\U0001f4cb Todo", callback_data='hist_todo'),
        ],
        [
            InlineKeyboardButton("\u2b05\ufe0f Volver al men\u00fa", callback_data='menu'),
        ]
    ])

# ------------------------------------
# STORAGE
# ------------------------------------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"registros": [], "chat_id": None, "flow": None}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

def clear_flow():
    data = load_data()
    data["flow"] = None
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

# ------------------------------------
# UTILIDADES
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

def escape_md(text):
    chars = r'_*[]()~`>#+-=|{}.!'
    for c in chars:
        text = text.replace(c, f'\\{c}')
    return text

async def enviar_pregunta(bot, chat_id, tipo, paso):
    preguntas = PREGUNTAS_SEMANAL if tipo == 'semanal' else PREGUNTAS_MENSUAL
    total = len(preguntas)
    titulo, pregunta = preguntas[paso]
    progreso = f"Pregunta {paso + 1} de {total}"
    tipo_label = "RETROALIMENTACI\u00d3N SEMANAL" if tipo == 'semanal' else "REFLEXI\u00d3N MENSUAL"

    texto = (
        f"\u26a1 *{escape_md(tipo_label)}*\n"
        f"\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
        f"_{escape_md(progreso)}_\n\n"
        f"*{escape_md(titulo)}*\n\n"
        f"{escape_md(pregunta)}\n\n"
        f"_Responde con calma\\. Estoy escuchando\\._ \U0001f447"
    )
    await bot.send_message(chat_id, texto, parse_mode='MarkdownV2')

# ------------------------------------
# COMANDOS
# ------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "\u2705 *Bot activado*\n\n"
        "Elige una opci\u00f3n o usa los comandos:\n"
        "/reporte \u2014 Retroalimentaci\u00f3n semanal\n"
        "/mensual \u2014 Reflexi\u00f3n mensual\n"
        "/capital \u2014 Divisi\u00f3n de capital\n"
        "/historial \u2014 Ver registros",
        parse_mode='MarkdownV2',
        reply_markup=menu_keyboard()
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f4cb *\u00bfQu\u00e9 quieres hacer?*",
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

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f4da *Historial \u2014 \u00bfQu\u00e9 categor\u00eda?*",
        parse_mode='MarkdownV2',
        reply_markup=historial_keyboard()
    )

def mostrar_registros(registros, titulo):
    if not registros:
        return f"\U0001f4da *{escape_md(titulo)}*\n\n_Sin registros a\u00fan\\._"
    texto = f"\U0001f4da *{escape_md(titulo)}*\n\n"
    for r in reversed(registros[-5:]):
        fecha = escape_md(r['fecha'])
        resp = escape_md(r['respuesta'][:300])
        texto += f"\U0001f4c5 _{fecha}_\n{resp}\n\n"
    return texto

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
            "\U0001f4da *Historial \u2014 \u00bfQu\u00e9 categor\u00eda?*",
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
    elif data == 'menu':
        await query.message.reply_text(
            "\U0001f4cb *\u00bfQu\u00e9 quieres hacer?*",
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )

# ------------------------------------
# MENSAJES DE TEXTO (respuestas)
# ------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow = get_flow()

    if flow:
        tipo = flow['tipo']
        paso = flow['paso']
        respuestas = flow.get('respuestas', [])
        preguntas = PREGUNTAS_SEMANAL if tipo == 'semanal' else PREGUNTAS_MENSUAL
        titulo, _ = preguntas[paso]

        respuestas.append(f"{titulo}: {update.message.text}")
        siguiente = paso + 1

        if siguiente < len(preguntas):
            set_flow(tipo, siguiente, respuestas)
            await enviar_pregunta(context.bot, update.effective_chat.id, tipo, siguiente)
        else:
            respuesta_completa = "\n\n".join(respuestas)
            guardar_registro(tipo, respuesta_completa)
            fecha = escape_md(datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M"))
            confirmacion = CONFIRMACIONES.get(tipo, "\u2705 *Guardado\\.*\n\n_Cada acci\u00f3n a tiempo cuenta\\._")
            await update.message.reply_text(
                f"{confirmacion}\n\n\u23f0 _{fecha}_",
                parse_mode='MarkdownV2',
                reply_markup=menu_keyboard()
            )

    elif get_esperando() == 'capital':
        guardar_registro('capital', update.message.text)
        fecha = escape_md(datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M"))
        confirmacion = CONFIRMACIONES['capital']
        await update.message.reply_text(
            f"{confirmacion}\n\n\u23f0 _{fecha}_",
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )

    else:
        await update.message.reply_text(
            "\U0001f4cb Usa el men\u00fa o escribe /menu",
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )

# ------------------------------------
# JOBS PROGRAMADOS
# ------------------------------------

async def job_semanal(context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id()
    if chat_id:
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

# ------------------------------------
# MAIN
# ------------------------------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("reporte", cmd_reporte))
    app.add_handler(CommandHandler("mensual", cmd_mensual))
    app.add_handler(CommandHandler("capital", cmd_capital))
    app.add_handler(CommandHandler("historial", cmd_historial))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    jq = app.job_queue
    mx = TIMEZONE

    jq.run_daily(job_semanal, time=dt_time(20, 30, tzinfo=mx), days=(3,), name="semanal")
    jq.run_daily(job_mensual, time=dt_time(8, 0, tzinfo=mx), days=(4,), name="mensual")
    jq.run_daily(job_capital, time=dt_time(8, 0, tzinfo=mx), name="capital")
    jq.run_daily(job_enviar_informe, time=dt_time(8, 0, tzinfo=mx), name="enviar_informe")
    jq.run_daily(job_pedir_informe, time=dt_time(20, 30, tzinfo=mx), name="pedir_informe")

    logger.info("Bot iniciado. Esperando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
