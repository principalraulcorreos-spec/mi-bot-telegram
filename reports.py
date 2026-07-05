# -*- coding: utf-8 -*-
"""Generacion de reportes y resumenes (semanal, mensual, por categoria,
listados de historial). Los reportes narrados por IA viven en ai_service.py
para evitar un import circular (necesitan groq_client)."""
from datetime import datetime, timedelta

from config import HABITOS, META_CAL_BASE, META_PASOS_DIARIO, PRESUPUESTO, TIMEZONE
from utils import escape_md
from storage import load_data
from domain import (
    get_gastos_mes, get_habitos_dias, get_ingresos_mes, get_movimientos_mes,
    get_salud_semana, get_stats_habs, get_streak, get_streaks,
)
from calendar_service import _listar_eventos_sync


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
    gym_dias       = stats.get("gym", 0)
    comida_dias    = stats.get("comida_casa", 0)
    trading_dias   = stats.get("trading_plan", 0)
    templanza_dias = stats.get("templanza", 0)

    meta_gym = 20  # meta mensual de gym
    gym_pct  = gym_dias / meta_gym * 100 if meta_gym else 0
    gym_icon = "✅" if gym_dias >= meta_gym * 0.8 else "⚠️" if gym_dias >= meta_gym * 0.5 else "🔴"

    # Semanas en el mes (promedio semanal)
    semanas = total_dias / 7 if total_dias >= 7 else 1
    gym_sem = round(gym_dias / semanas, 1) if semanas else gym_dias

    comida_pct = round(comida_dias / total_dias * 100) if total_dias else 0
    comida_icon = "✅" if comida_pct >= 80 else "⚠️" if comida_pct >= 50 else "🔴"

    templanza_pct  = round(templanza_dias / total_dias * 100) if total_dias else 0
    templanza_icon = "✅" if templanza_pct >= 80 else "⚠️" if templanza_pct >= 50 else "🔴"

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
        f"  {gym_icon} Gym: {gym_dias} días \\({escape_md(str(gym_sem))} días/semana\\)\n"
        f"  {comida_icon} Comida en casa: {comida_dias} días \\({comida_pct}%\\)\n"
        f"  📈 Trading según plan: {trading_dias} días\n"
        f"  {templanza_icon} Templanza: {templanza_dias} días \\({templanza_pct}%\\)\n"
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

