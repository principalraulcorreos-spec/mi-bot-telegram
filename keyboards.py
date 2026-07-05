# -*- coding: utf-8 -*-
"""Teclados (botones) inline de Telegram usados en todo el bot."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import EMOCIONES_TRADE


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


def undo_keyboard(tipo, token):
    """Botón deshacer para acciones que el bot auto-ejecuta sin pedir confirmación
    (nota/pasos/calorías/peso). token identifica la entrada exacta a borrar."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Deshacer", callback_data=f'undo:{tipo}:{token}')]
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

