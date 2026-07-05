# -*- coding: utf-8 -*-
"""Logica de negocio: registrar y consultar gastos, habitos, trades, salud,
recordatorios, etc. No sabe nada de Telegram ni de IA."""
import re
from datetime import datetime, time as dt_time, timedelta

from config import (
    CATEGORIAS_ALIAS, CORTE_CABELLO_BASE, HABITOS, META_CAL_BASE,
    PRESUPUESTO, TIMEZONE,
)
from utils import escape_md
from storage import load_data, save_data


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


def registrar_habito(respuestas):
    data = load_data()
    data["habitos"].append({
        "fecha": datetime.now(TIMEZONE).strftime("%Y-%m-%d"),
        "respuestas": respuestas,
    })
    data["habito_flow"] = None; save_data(data)


def guardar_nota(texto):
    data = load_data()
    fecha = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    data["notas"].append({"fecha": fecha, "texto": texto})
    save_data(data)
    return fecha


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

