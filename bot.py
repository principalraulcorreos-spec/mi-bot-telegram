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
# MENSAJES — PREGUNTAS
# ------------------------------------

SEMANAL = (
    "\U0001f6a8 *\u00bfES JUEVES POR LA NOCHE\\?*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f4ca *RETROALIMENTACI\u00d3N SEMANAL*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n\n"
    "1\ufe0f\u20e3 *EL PULSO DE LA SEMANA*\n"
    "\u2022 Control vs Reacci\u00f3n: \u00bf80% control o me arrastr\u00f3 la semana?\n"
    "\u2022 Emoci\u00f3n dominante: \u00bfCalma o ansiedad?\n"
    "\u2022 \u00bfD\u00f3nde estuve a punto de traicionarme?\n\n"
    "2\ufe0f\u20e3 *DINERO Y EL RA\u00daL DEL FUTURO*\n"
    "\u2022 \u00bfQu\u00e9 % de mis gastos fueron fugas?\n"
    "\u2022 \u00bfLe rob\u00e9 al Ra\u00fal del futuro? \u00bfCu\u00e1l fue el disparador?\n"
    "\u2022 \u00bfEn qu\u00e9 momento dije NO a un gasto impulsivo?\n\n"
    "3\ufe0f\u20e3 *SISTEMAS Y TRADING*\n"
    "\u2022 Del 1 al 10, \u00bfcu\u00e1nto respet\u00e9 mi estrategia?\n"
    "\u2022 \u00bfCerr\u00e9 trades por miedo o incomodidad?\n"
    "\u2022 \u00bfEsper\u00e9 mi configuraci\u00f3n o forc\u00e9 entradas?\n\n"
    "4\ufe0f\u20e3 *TEMPLANZA E IMPULSOS*\n"
    "\u2022 \u00bfCed\u00ed a impulsos carnales o transmit\u00ed esa energ\u00eda?\n"
    "\u2022 \u00bfCom\u00ed en casa seg\u00fan lo planeado?\n\n"
    "5\ufe0f\u20e3 *HUMILDAD Y CAR\u00c1CTER*\n"
    "\u2022 \u00bfReconoc\u00ed que a\u00fan estoy aprendiendo?\n"
    "\u2022 \u00bfAcept\u00e9 correcci\u00f3n o me defend\u00ed por orgullo silencioso?\n\n"
    "6\ufe0f\u20e3 *RELACIONES Y PAZ*\n"
    "\u2022 \u00bfFui un apoyo real para mi familia y amigos?\n"
    "\u2022 \u00bfHabl\u00e9 desde la verdad o desde el c\u00e1lculo?\n\n"
    "7\ufe0f\u20e3 *CIERRE*\n"
    "\u2022 Calificaci\u00f3n de la semana \\(1\u201310\\): \\_\\_\\_\n"
    "\u2022 \u00bfQu\u00e9 UNA cosa har\u00e9 diferente el lunes?\n\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f4dd *Responde ahora\\. No lo dejes para despu\u00e9s\\.* \U0001f447"
)

MENSUAL = (
    "\U0001f6a8 *\u00bfES EL \u00daLTIMO VIERNES DEL MES\\?*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f9e0 *REFLEXI\u00d3N MENSUAL*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n\n"
    "1\ufe0f\u20e3 *ESTE MES, \u00bfC\u00d3MO VIV\u00cd?*\n"
    "\u2022 \u00bfRespond\u00ed a la vida o la dirig\u00ed?\n"
    "\u2022 \u00bfQu\u00e9 emoci\u00f3n domin\u00f3 m\u00e1s mis d\u00edas?\n"
    "\u2022 \u00bfEn qu\u00e9 momentos me traicion\u00e9?\n\n"
    "2\ufe0f\u20e3 *DINERO*\n"
    "\u2022 \u00bfMi dinero me dio paz o estr\u00e9s este mes?\n"
    "\u2022 \u00bfGast\u00e9 con intenci\u00f3n o por impulso?\n"
    "\u2022 \u00bfQu\u00e9 decisi\u00f3n financiera repetir\u00eda? \u00bfCu\u00e1l no?\n\n"
    "3\ufe0f\u20e3 *DISCIPLINA Y H\u00c1BITOS*\n"
    "\u2022 \u00bfQu\u00e9 h\u00e1bito peque\u00f1o s\u00ed cumpl\u00ed?\n"
    "\u2022 \u00bfD\u00f3nde me ment\u00ed diciendo \"luego\"?\n"
    "\u2022 \u00bfQu\u00e9 h\u00e1bito sostenido 30 d\u00edas m\u00e1s me cambiar\u00eda el a\u00f1o?\n\n"
    "4\ufe0f\u20e3 *RELACIONES*\n"
    "\u2022 \u00bfA qui\u00e9n cuid\u00e9 de verdad?\n"
    "\u2022 \u00bfFui refugio emocional o carga?\n\n"
    "5\ufe0f\u20e3 *FE / VIDA INTERIOR*\n"
    "\u2022 \u00bfEste mes conf\u00ed incluso sin entender?\n"
    "\u2022 \u00bfQu\u00e9 agradezco sinceramente?\n\n"
    "6\ufe0f\u20e3 *BALANCE MENSUAL*\n"
    "Califica del 1 al 10: Orden / Paz / Avance / Honestidad / Humildad\n\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f51a _\"Este mes aprend\u00ed que \\_\\_\\_\\.\"_\n"
    "_\"El pr\u00f3ximo mes me enfocar\u00e9 en \\_\\_\\_\\.\"_\n\n"
    "\U0001f4dd *Responde ahora\\. No lo dejes para despu\u00e9s\\.* \U0001f447"
)

CAPITAL = (
    "\U0001f6a8 *\u00bfES D\u00cdA 1 DEL MES\\?*\n"
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
    "\U0001f6a8 *RECORDATORIO: PEDIR INFORMES*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n\n"
    "\U0001f4f1 Manda este WhatsApp a los hermanos *ahora*:\n\n"
    "_\"Hermanos, ya es fin de mes\\. Por favor env\u00edenme su informe cuando puedan\\. Gracias\\.\"_\n\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\u26a0\ufe0f *No lo dejes para ma\u00f1ana\\.*"
)

ENVIAR_INFORME = (
    "\U0001f6a8 *\u00daLTIMO D\u00cdA \u2014 ENVIAR INFORME*\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n\n"
    "\u26a0\ufe0f Hoy es el d\u00eda 4\\. *L\u00edmite hoy\\.* \u26a0\ufe0f\n\n"
    "Recopila los informes recibidos y env\u00edalos\n"
    "a la persona correspondiente de la congregaci\u00f3n\\.\n\n"
    "\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
    "\U0001f4e4 *H\u00e1zlo antes de las 12PM\\.* \u23f0"
)

# ------------------------------------
# TECLADO DE BOTONES
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

# ------------------------------------
# STORAGE
# ------------------------------------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"registros": [], "chat_id": None, "esperando": None}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_chat_id():
    return load_data().get("chat_id")

def set_chat_id(chat_id):
    data = load_data()
    data["chat_id"] = chat_id
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
        "/historial \u2014 Ver \u00faltimos registros",
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
    set_esperando('semanal')
    await update.message.reply_text(SEMANAL, parse_mode='MarkdownV2')

async def cmd_mensual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_esperando('mensual')
    await update.message.reply_text(MENSUAL, parse_mode='MarkdownV2')

async def cmd_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_esperando('capital')
    await update.message.reply_text(CAPITAL, parse_mode='MarkdownV2')

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    registros = data.get("registros", [])
    if not registros:
        await update.message.reply_text(
            "No hay registros a\u00fan\\.",
            parse_mode='MarkdownV2',
            reply_markup=menu_keyboard()
        )
        return
    ultimos = registros[-5:]
    texto = "\U0001f4da *\u00daltimos registros:*\n\n"
    for r in reversed(ultimos):
        fecha = escape_md(r['fecha'])
        tipo = escape_md(r['tipo'])
        resp = escape_md(r['respuesta'][:200])
        texto += f"\U0001f4c5 *{fecha}* \u2014 {tipo}\n_{resp}_\n\n"
    await update.message.reply_text(texto, parse_mode='MarkdownV2', reply_markup=menu_keyboard())

# ------------------------------------
# CALLBACK DE BOTONES
# ------------------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'reporte':
        set_esperando('semanal')
        await query.message.reply_text(SEMANAL, parse_mode='MarkdownV2')
    elif data == 'mensual':
        set_esperando('mensual')
        await query.message.reply_text(MENSUAL, parse_mode='MarkdownV2')
    elif data == 'capital':
        set_esperando('capital')
        await query.message.reply_text(CAPITAL, parse_mode='MarkdownV2')
    elif data == 'historial':
        load = load_data()
        registros = load.get("registros", [])
        if not registros:
            await query.message.reply_text(
                "No hay registros a\u00fan\\.",
                parse_mode='MarkdownV2',
                reply_markup=menu_keyboard()
            )
            return
        ultimos = registros[-5:]
        texto = "\U0001f4da *\u00daltimos registros:*\n\n"
        for r in reversed(ultimos):
            fecha = escape_md(r['fecha'])
            tipo = escape_md(r['tipo'])
            resp = escape_md(r['respuesta'][:200])
            texto += f"\U0001f4c5 *{fecha}* \u2014 {tipo}\n_{resp}_\n\n"
        await query.message.reply_text(texto, parse_mode='MarkdownV2', reply_markup=menu_keyboard())

# ------------------------------------
# MENSAJES DE TEXTO (respuestas)
# ------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = get_esperando()
    if tipo:
        guardar_registro(tipo, update.message.text)
        fecha = escape_md(datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M"))
        await update.message.reply_text(
            f"\u2705 *Guardado* \\({escape_md(tipo)}\\) \u2014 {fecha}\n\n"
            "_Sigue adelante\\. Cada registro es un paso\\._ \U0001f4aa",
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
# JOBS PROGRAMADOS (automaticos)
# ------------------------------------

async def job_semanal(context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id()
    if chat_id:
        set_esperando('semanal')
        await context.bot.send_message(chat_id, SEMANAL, parse_mode='MarkdownV2')

async def job_mensual(context: ContextTypes.DEFAULT_TYPE):
    if es_ultimo_viernes():
        chat_id = get_chat_id()
        if chat_id:
            set_esperando('mensual')
            await context.bot.send_message(chat_id, MENSUAL, parse_mode='MarkdownV2')

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
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    jq = app.job_queue
    mx = TIMEZONE

    # Jueves 8:30PM — retroalimentacion semanal (automatico)
    jq.run_daily(job_semanal, time=dt_time(20, 30, tzinfo=mx), days=(3,), name="semanal")
    # Viernes 8AM — reflexion mensual si es el ultimo viernes
    jq.run_daily(job_mensual, time=dt_time(8, 0, tzinfo=mx), days=(4,), name="mensual")
    # Diario 8AM — capital (dia 1) y enviar informe (dia 4)
    jq.run_daily(job_capital, time=dt_time(8, 0, tzinfo=mx), name="capital")
    jq.run_daily(job_enviar_informe, time=dt_time(8, 0, tzinfo=mx), name="enviar_informe")
    # Diario 8:30PM — pedir informe (dia 30)
    jq.run_daily(job_pedir_informe, time=dt_time(20, 30, tzinfo=mx), name="pedir_informe")

    logger.info("Bot iniciado. Esperando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
