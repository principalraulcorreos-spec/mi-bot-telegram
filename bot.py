# -*- coding: utf-8 -*-
"""
Punto de entrada del bot: handlers de comandos/mensajes/botones, jobs
programados y arranque de la aplicacion de Telegram.
"""
import asyncio
import io
import json
import logging
import os
import re
from datetime import datetime, time as dt_time, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from config import (
    TOKEN, TIMEZONE, CATEGORIAS_ALIAS, GASTO_RE, HABITOS,
    RUTINA_LMV, META_PASOS_DIARIO, META_CAL_BASE, _calcular_meta_calorias,
    PREGUNTAS_SEMANAL, PREGUNTAS_MENSUAL, PRESUPUESTO,
    PEDIR_INFORME, ENVIAR_INFORME,
)
from utils import escape_md, frase_aleatoria, streak_text, es_ultimo_viernes, dia_hoy
from storage import (
    load_data, save_data,
    get_chat_id, set_chat_id, get_flow, set_flow, get_esperando,
    set_razonar_pending, get_razonar_pending, clear_razonar_pending,
    set_habito_flow, get_trade_pending, clear_trade_pending,
    get_ai_history, save_ai_history,
    set_pending_action, get_pending_action, clear_pending_action, clear_all_flows,
    get_sofia_mode, set_sofia_mode, get_sofia_history, save_sofia_history,
)
from domain import (
    guardar_registro, registrar_gasto, registrar_ingreso, registrar_movimiento, check_budget_alert,
    get_gastos_mes, get_streaks,
    guardar_nota,
    get_open_trade, guardar_trade_entrada, cerrar_trade,
    registrar_pasos, registrar_calorias, get_salud_hoy, get_salud_semana, es_semana_corte,
    guardar_recordatorio, eliminar_recordatorio, _parse_recordatorio,
    registrar_habito,
    get_ingresos_mes,
)
from keyboards import (
    menu_keyboard, finanzas_keyboard, trading_keyboard, salud_keyboard, agenda_keyboard,
    reportes_keyboard, historial_keyboard, habito_keyboard, confirm_keyboard, undo_keyboard,
    emocion_trade_keyboard, estrategia_keyboard,
    gmail_tipo_keyboard,
)
from ai_service import (
    call_ai, call_sofia, parse_ai_response,
    _transcribe_sync, _analyze_receipt_sync, parse_receipt,
    _generar_reporte_sofia_mensual_sync, _generar_reporte_sofia_anual_sync,
    _generar_reporte_financiero_anual_sync,
)
from calendar_service import _listar_eventos_sync, _crear_evento_sync, formatear_eventos
from gmail_service import _fetch_gmail_transactions_sync
from forex_service import _send_noticias
from reports import (
    generar_resumen_semanal, generar_resumen_gastos, generar_como_voy,
    generar_reporte_global_mensual,
    mostrar_registros, mostrar_trades, mostrar_notas, mostrar_ingresos_mes, mostrar_balance_mes,
    mostrar_movimientos_mes, mostrar_stats_trading, generar_habitos_mes,
    _consultar_rango, _formato_peso,
)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


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
        msg_esc = escape_md(message_text) if message_text else ""
        await update.message.reply_text(
            f"{msg_esc}\n\n💰 ¿Registro *{monto_esc}* como ingreso \\({tipo_esc}\\)?",
            parse_mode='MarkdownV2',
            reply_markup=confirm_keyboard()
        )
    elif action and action["type"] == "movimiento":
        set_pending_action(action)
        monto_esc = escape_md(f"${action['amount']:,.0f}")
        desc_esc  = escape_md(action['descripcion'])
        msg_esc = escape_md(message_text) if message_text else ""
        await update.message.reply_text(
            f"{msg_esc}\n\n🔄 ¿Registro *{monto_esc}* como movimiento entre cuentas?\n_{desc_esc}_",
            parse_mode='MarkdownV2',
            reply_markup=confirm_keyboard()
        )
    elif action and action["type"] == "razonar":
        # Guardar el mensaje original y preguntar para clarificar
        set_razonar_pending(text, action["pregunta"])
        pregunta_esc = escape_md(action["pregunta"])
        msg_esc = escape_md(message_text) if message_text else ""
        resp_text = f"{msg_esc}\n\n🤔 _{pregunta_esc}_" if message_text else f"🤔 _{pregunta_esc}_"
        await update.message.reply_text(resp_text, parse_mode='MarkdownV2')
    elif action and action["type"] == "nota":
        nota_fecha = guardar_nota(action["texto"])
        await update.message.reply_text(
            f"{escape_md(message_text)}\n\n📝 _Nota guardada\\._",
            parse_mode='MarkdownV2',
            reply_markup=undo_keyboard('nota', nota_fecha)
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
            resp = escape_md("No pude crear el evento. Verifica que el calendario esté conectado.")
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
        fecha_hoy = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        if message_text:
            await update.message.reply_text(message_text)
        await update.message.reply_text(resp, parse_mode='MarkdownV2',
                                         reply_markup=undo_keyboard('pasos', fecha_hoy))
    elif action and action["type"] == "calorias":
        registrar_calorias(action["valor"])
        data_sal = load_data()
        meta_c = data_sal.get("meta_calorias", META_CAL_BASE)
        icon = "🔥" if action["valor"] >= meta_c * 0.3 else "⚡"
        resp = f"{icon} *{action['valor']} kcal quemadas* registradas"
        fecha_hoy = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        if message_text:
            await update.message.reply_text(message_text)
        await update.message.reply_text(resp, parse_mode='MarkdownV2',
                                         reply_markup=undo_keyboard('calorias', fecha_hoy))
    else:
        await update.message.reply_text(message_text)


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
                nota_fecha = guardar_nota(action["texto"])
                await update.message.reply_text(
                    f"{message_text}\n\n📝 Nota guardada.",
                    reply_markup=undo_keyboard('nota', nota_fecha)
                )
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
    _peso_match = _re.search(r'\bpes[oée]\s+(\d+(?:[.,]\d+)?)', _tl)
    if not _peso_match:
        # "N kg" pero no "N kg de <algo>" (evita confundir compras: "2 kg de arroz")
        _peso_match = _re.search(r'\b(\d+(?:[.,]\d+)?)\s*kg\b(?!\s*(?:de|d[eé])\b)', _tl)
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
                await update.message.reply_text(texto, parse_mode='MarkdownV2',
                                                 reply_markup=undo_keyboard('peso', fecha))
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
                fecha_hoy = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
                await update.message.reply_text(
                    f"{icon} *{val:,} pasos* registrados \\({meta_pct}% de la meta diaria\\)",
                    parse_mode='MarkdownV2',
                    reply_markup=undo_keyboard('pasos', fecha_hoy)
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
                fecha_hoy = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
                await update.message.reply_text(
                    f"🔥 *{val} kcal quemadas* registradas",
                    parse_mode='MarkdownV2',
                    reply_markup=undo_keyboard('calorias', fecha_hoy)
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

    elif data.startswith('undo:'):
        _, tipo, token = data.split(':', 2)
        d = load_data()
        if tipo == 'pasos':
            d['pasos'] = [p for p in d.get('pasos', []) if p['fecha'] != token]
        elif tipo == 'calorias':
            d['calorias'] = [c for c in d.get('calorias', []) if c['fecha'] != token]
        elif tipo == 'peso':
            d['peso'] = [p for p in d.get('peso', []) if p['fecha'] != token]
        elif tipo == 'nota':
            d['notas'] = [n for n in d.get('notas', []) if n['fecha'] != token]
        save_data(d)
        await query.answer("↩️ Deshecho")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text("↩️ Se deshizo el registro anterior.")

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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_text_message(update, context, update.message.text or "")


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


async def job_briefing_matutino(context: ContextTypes.DEFAULT_TYPE):
    """Briefing unificado 6:15am: agenda + finanzas + hábitos + salud en un solo
    mensaje, para tener el panorama completo del día sin revisar cada módulo aparte."""
    chat_id = get_chat_id()
    if not chat_id:
        return
    try:
        data = load_data()
        now  = datetime.now(TIMEZONE)

        try:
            eventos    = await asyncio.to_thread(_listar_eventos_sync, 1)
            agenda_txt = formatear_eventos(eventos)
        except Exception:
            agenda_txt = "_Agenda no disponible\\._"

        gastos_mes    = get_gastos_mes()
        total_gastado = sum(g["cantidad"] for g in gastos_mes)
        total_presup  = sum(PRESUPUESTO.values())
        pct_mes       = (total_gastado / total_presup * 100) if total_presup else 0

        streaks = get_streaks()
        streak_lines = []
        for clave, label in HABITOS:
            s = streaks.get(clave, 0)
            if s >= 2:
                short = label.split('¿')[-1].rstrip('?').strip() if '¿' in label else label
                streak_lines.append(f"{escape_md(short)}: {s}🔥")
        streak_txt = ", ".join(streak_lines) if streak_lines else "_sin rachas activas_"

        salud_hoy = get_salud_hoy()
        salud_sem = get_salud_semana()
        peso_txt  = f"{salud_hoy['peso']:.1f} kg" if salud_hoy["peso"] else "sin registrar"
        pasos_avg = f"{salud_sem['avg_pasos']:,}" if salud_sem["avg_pasos"] else "—"

        recs_activos = len([r for r in data.get("recordatorios", []) if r.get("activo", True)])

        texto = (
            f"☀️ *BUENOS DÍAS, RAÚL* — {escape_md(now.strftime('%A %d/%m'))}\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"📅 *Agenda de hoy:*\n{agenda_txt}\n\n"
            f"💰 *Mes:* ${total_gastado:.0f} gastados \\({pct_mes:.0f}% del presupuesto total\\)\n\n"
            f"💪 *Rachas:* {streak_txt}\n\n"
            f"⚖️ *Salud:* {escape_md(peso_txt)} · pasos/día \\(prom\\.\\): {escape_md(pasos_avg)}\n\n"
            f"⏰ *Recordatorios activos:* {recs_activos}\n\n"
            f"_Vamos con todo hoy\\._"
        )
        await context.bot.send_message(chat_id, texto, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"job_briefing_matutino error: {e}")


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


async def job_backup_semanal(context: ContextTypes.DEFAULT_TYPE):
    """Domingo 9pm México — manda el registro completo (Supabase o archivo local) como documento."""
    if datetime.now(TIMEZONE).weekday() != 6:  # 6 = domingo
        return
    chat_id = get_chat_id()
    if not chat_id:
        return
    data = load_data()
    if not data:
        return
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    buffer = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    buffer.name = f"registro_backup_{fecha}.json"
    await context.bot.send_document(
        chat_id=chat_id,
        document=buffer,
        filename=f"registro_backup_{fecha}.json",
        caption=f"💾 Backup semanal — {fecha}"
    )


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


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Captura cualquier excepción no manejada en un handler/job.
    Sin esto, un error se perdía en el log y el usuario se quedaba sin
    respuesta (sensación de 'no hay lógica' / bot que no reacciona)."""
    logger.error("Excepción no manejada", exc_info=context.error)
    try:
        chat_id = None
        if isinstance(update, Update) and update.effective_chat:
            chat_id = update.effective_chat.id
        else:
            chat_id = get_chat_id()
        if chat_id:
            await context.bot.send_message(
                chat_id,
                "⚠️ Tuve un error procesando eso. Ya quedó registrado en el log, intenta de nuevo."
            )
    except Exception:
        pass  # si ni siquiera se puede avisar, no hay más que hacer aquí


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_error_handler(error_handler)

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
    jq.run_daily(job_briefing_matutino, time=dt_time(6, 15, tzinfo=mx),          name="briefing_matutino")
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

