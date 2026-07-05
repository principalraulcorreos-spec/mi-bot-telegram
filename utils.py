# -*- coding: utf-8 -*-
"""Funciones auxiliares genericas (texto, fechas, frases)."""
import random
from calendar import monthcalendar, FRIDAY
from datetime import datetime

from config import FRASES_RAW, HABITOS, TIMEZONE


def escape_md(text):
    chars = r'_*[]()~`>#+-=|{}.!'
    for c in chars:
        text = str(text).replace(c, f'\\{c}')
    return text


def frase_aleatoria():
    return escape_md(random.choice(FRASES_RAW))


def streak_text(streaks):
    lines = ""
    labels = {clave: label.split("¿")[-1].rstrip("?").strip() if "¿" in label else label
              for clave, label in HABITOS}
    for clave, s in streaks.items():
        if s >= 2:
            lines += f"🔥 {s} días seguidos: {escape_md(labels[clave])}\n"
    return lines


def es_ultimo_viernes():
    today = datetime.now(TIMEZONE).date()
    if today.weekday() != 4:
        return False
    weeks = monthcalendar(today.year, today.month)
    ultimo_viernes = max(w[FRIDAY] for w in weeks if w[FRIDAY] != 0)
    return today.day == ultimo_viernes


def dia_hoy():
    return datetime.now(TIMEZONE).day


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

