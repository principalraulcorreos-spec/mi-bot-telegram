# -*- coding: utf-8 -*-
"""
Integracion con la IA (Groq): construccion de prompts, llamadas al modelo,
parseo de respuestas, transcripcion de voz, analisis de fotos de recibos y
de trades, y generacion de reportes narrados por la IA (mensual/anual).
"""
import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime

from groq import Groq

from config import HABITOS, META_PASOS_DIARIO, PRESUPUESTO, TIMEZONE
from storage import load_data, get_sofia_context_summary
from domain import (
    get_gastos_mes, get_habitos_dias, get_ingresos_mes, get_movimientos_mes,
    get_open_trade, get_salud_hoy, get_stats_habs, get_streaks,
)
from reports import _build_historial_compacto
from calendar_service import get_calendar_context

logger = logging.getLogger(__name__)


groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))


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

    # Ingresos y movimientos del mes
    stats_habs     = get_stats_habs()
    ingresos_mes   = get_ingresos_mes()
    movimientos_mes = get_movimientos_mes()
    total_ingresos = sum(i["cantidad"] for i in ingresos_mes)
    total_movs     = sum(m["cantidad"] for m in movimientos_mes)
    total_gastos_mes = sum(gastos_por_cat.values())
    balance_mes    = total_ingresos - total_gastos_mes

    ingresos_str   = "\n".join([f"  {i['fecha'][:10]}: ${i['cantidad']:.0f} ({i.get('tipo','')})"
                                 for i in ingresos_mes[-5:]]) or "  ninguno"
    movs_str       = "\n".join([f"  {m['fecha'][:10]}: ${m['cantidad']:.0f} ({m.get('descripcion','')})"
                                 for m in movimientos_mes[-5:]]) or "  ninguno"

    # Alertas coach
    coach_alerts = []
    gym_dias   = stats_habs.get("gym", 0)
    total_dias = stats_habs.get("total_dias", 0)
    comida_dias = stats_habs.get("comida_casa", 0)
    if total_dias >= 7:
        gym_sem = gym_dias / (total_dias / 7)
        if gym_sem < 3:
            coach_alerts.append(f"ALERTA GYM: solo {gym_dias} días de gym este mes ({gym_sem:.1f}/semana). Meta: ≥3/semana.")
        comida_pct = comida_dias / total_dias * 100
        if comida_pct < 60:
            coach_alerts.append(f"ALERTA COMIDA: solo {comida_pct:.0f}% comiendo en casa. Gasto innecesario.")
    if total_gastos_mes > total_ingresos > 0:
        coach_alerts.append(f"ALERTA FINANZAS: gastos (${total_gastos_mes:.0f}) > ingresos (${total_ingresos:.0f}) este mes.")
    cap_gasto = gastos_por_cat.get("capricho", 0)
    if cap_gasto > PRESUPUESTO.get("capricho", 500) * 1.2:
        coach_alerts.append(f"ALERTA CAPRICHOS: ${cap_gasto:.0f} en caprichos (sobre presupuesto).")

    coach_str = "\n".join(coach_alerts) if coach_alerts else "  Sin alertas activas."

    historial_compacto = _build_historial_compacto()

    return f"""Eres el asistente personal de Raúl — su coach de vida, entrenador y checador de plenitud integrado en Telegram.

PERFIL DE RAÚL:
- Trader activo, usa estrategia Mark Jeffrey
- Testigo de Jehová, comprometido con su fe
- Vive con su abuelo, lo cuida
- Renta mensual fija: $8,000 pesos
- TikToker y creador de contenido
- Novia: Nallelita
- Trabaja activamente en disciplinarse: hábitos, dinero y trading

CONTEXTO ACTUAL ({now.strftime('%d/%m/%Y %H:%M')} Ciudad de México):
- Semanas de retroalimentación: {num_semanas}

HISTORIAL COMPACTO (últimos 3 meses + detalle 30 días):
{historial_compacto}

FINANZAS DEL MES:
- Gastos por categoría: {json.dumps(gastos_por_cat, ensure_ascii=False) if gastos_por_cat else 'ninguno'}
- Total gastos: ${total_gastos_mes:.0f} | Ingresos: ${total_ingresos:.0f} | Balance: ${balance_mes:+.0f}
- Últimos ingresos:
{ingresos_str}
- Movimientos entre cuentas:
{movs_str}
- Últimos gastos:
{gastos_str}

HÁBITOS ESTE MES (días registrados: {total_dias}):
  gym: {gym_dias} días | {habitos_resumen.get('gym','sin datos')} (últimos 7 días)
  comida en casa: {comida_dias} días | {habitos_resumen.get('comida_casa','sin datos')} (últimos 7 días)
  trading según plan: {stats_habs.get('trading_plan',0)} días | {habitos_resumen.get('trading_plan','sin datos')} (últimos 7 días)
  templanza (no masturbación): {stats_habs.get('templanza',0)} días | {habitos_resumen.get('templanza','sin datos')} (últimos 7 días)

TRADES:
- Abierto: {open_str}
- Recientes:
{trades_str}

NOTAS:
{notas_str}

AGENDA 48H:
{get_calendar_context()}

ALERTAS DEL COACH:
{coach_str}

SALUD HOY (Samsung Watch):
{_build_salud_context()}

INSTRUCCIONES COMO COACH:
- Habla de tú, español mexicano, informal pero directo con carácter
- Eres SU asistente — conoces su vida, sus metas, sus puntos débiles
- Respuestas cortas (3-4 líneas). Sin markdown.
- Si detectas que un área está decayendo, señálalo proactivamente aunque no te pregunte
- Conecta lo que dice con su contexto (trading, fe, abuelo, Nallelita, disciplina)
- NUNCA cuestiones lo que Raúl dice de su vida personal. Acéptalo y ayúdalo.
- Antes de registrar algo importante, puedes hacer UNA pregunta inteligente para clarificar
- Horario scalper: lunes a viernes 7-10am. Análisis semanal: viernes 12:45-1:30pm.
- Rutina gym: lunes, miércoles y viernes.

DETECCIÓN DE ACCIONES — incluye al final (línea separada) si aplica:

Si detectas un GASTO con monto MAYOR A CERO (nunca generes esto si no hay monto explícito):
ACCION_GASTO:[monto]:[categoria]
Categorías: comida, transporte, capricho, salud, otros

Si detectas un INGRESO con monto:
ACCION_INGRESO:[monto]:[tipo]
Tipos: renta, transferencia, rendimientos, otro

Si detectas MOVIMIENTO entre cuentas:
ACCION_MOVIMIENTO:[monto]:[descripcion]

Si quiere guardar una nota:
ACCION_NOTA:[texto]

Si quiere VER agenda:
ACCION_CAL_VER:[dias]

Si quiere CREAR evento:
ACCION_CAL_CREAR:[titulo]|[YYYY-MM-DD]|[HH:MM]|[duracion_minutos]

Si detecta pasos del día (Samsung Watch o manual):
ACCION_PASOS:[numero_entero]

Si detecta calorías quemadas del día:
ACCION_CALORIAS:[numero_entero]

Si el usuario pregunta por datos de un rango de fechas específico que NO tienes disponible (ej: "del 5 al 20 de marzo", "la primera semana de abril"):
ACCION_CONSULTA:[modulo]:[YYYY-MM-DD]:[YYYY-MM-DD]
Módulos: gastos | ingresos | finanzas | habitos | trades | peso | salud | todo

Si necesitas UNA pregunta de clarificación ANTES de registrar algo (solo para info importante/ambigua):
ACCION_RAZONAR:[pregunta concreta y específica]

IMPORTANTE — razonamiento con datos:
- Ya tienes el historial compacto de los últimos 3 meses en el prompt.
- Si preguntan de "esta semana", "hoy", "este mes" o "últimos 30 días" — responde directamente con los datos que ya tienes.
- Solo usa ACCION_CONSULTA cuando necesites datos de un rango específico que no está en el historial compacto.
- Puedes responder preguntas como "¿hice gym esta semana?", "¿cuánto gasté en comida?", "¿cuál fue mi mejor semana?" directamente con los datos del historial.

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
                    amt = float(parts[1].strip())
                    if amt > 0:
                        action = {"type": "gasto", "amount": amt, "category": parts[2].strip().lower()}
                except Exception:
                    clean.append(line)
        elif line.startswith('ACCION_INGRESO:'):
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    action = {"type": "ingreso", "amount": float(parts[1].strip()), "tipo": parts[2].strip().lower()}
                except Exception:
                    clean.append(line)
        elif line.startswith('ACCION_MOVIMIENTO:'):
            parts = line.split(':', 2)
            if len(parts) >= 3:
                try:
                    action = {"type": "movimiento", "amount": float(parts[1].strip()), "descripcion": parts[2].strip()}
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
        elif line.startswith('ACCION_RAZONAR:'):
            pregunta = line[len('ACCION_RAZONAR:'):].strip()
            if pregunta:
                action = {"type": "razonar", "pregunta": pregunta}
        elif line.startswith('ACCION_CONSULTA:'):
            partes = line[len('ACCION_CONSULTA:'):].strip().split(':')
            if len(partes) >= 3:
                action = {"type": "consulta", "modulo": partes[0].strip(),
                          "fecha_ini": partes[1].strip(), "fecha_fin": partes[2].strip()}
        elif line.startswith('ACCION_PASOS:'):
            val_str = line[len('ACCION_PASOS:'):].strip()
            try:
                action = {"type": "pasos", "valor": int(float(val_str))}
            except Exception:
                clean.append(line)
        elif line.startswith('ACCION_CALORIAS:'):
            val_str = line[len('ACCION_CALORIAS:'):].strip()
            try:
                action = {"type": "calorias", "valor": int(float(val_str))}
            except Exception:
                clean.append(line)
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
- Integras lo que Raúl ha compartido en sesiones PASADAS y presentes — tienes memoria continua
- Si detectas patrones que se repiten de sesiones anteriores, nómbralos con cuidado

HISTORIAL ACUMULADO DE SESIONES PASADAS:
{get_sofia_context_summary()}

Fecha: {now.strftime('%A %d/%m/%Y %H:%M')} (Ciudad de México)"""


def _call_sofia_sync(user_message: str, history: list) -> str:
    messages = (
        [{"role": "system", "content": build_sofia_system_prompt()}]
        + history
        + [{"role": "user", "content": user_message}]
    )
    resp = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
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


def _build_salud_context() -> str:
    s = get_salud_hoy()
    lines = []
    if s["peso"]:
        lines.append(f"  Peso: {s['peso']:.1f} kg | Meta calorías: {s['meta_calorias']} kcal/día")
    pasos_txt = f"{s['pasos']:,}" if s["pasos"] else "no registrado"
    cal_txt   = f"{s['calorias']} kcal" if s["calorias"] else "no registrado"
    meta_p    = META_PASOS_DIARIO
    pasos_pct = f" ({round(s['pasos']/meta_p*100)}% meta)" if s["pasos"] else ""
    lines.append(f"  Pasos hoy: {pasos_txt}{pasos_pct} | Calorías quemadas: {cal_txt}")
    return "\n".join(lines) if lines else "  Sin datos de salud hoy."


def _transcribe_sync(audio_bytes: bytes) -> str:
    transcription = groq_client.audio.transcriptions.create(
        file=("audio.ogg", audio_bytes),
        model="whisper-large-v3",
        response_format="text",
        language="es",
    )
    return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()


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


def _generar_reporte_sofia_mensual_sync(año=None, mes=None) -> str:
    """Llama a Groq para generar el análisis emocional mensual de Sofía."""
    data = load_data()
    history = data.get("sofia_history", [])
    if not history:
        return None

    now = datetime.now(TIMEZONE)
    año = año or now.year
    mes = mes or now.month
    if now.day == 1 and año == now.year and mes == now.month:
        if mes == 1: año -= 1; mes = 12
        else: mes -= 1

    import calendar
    nombre_mes = calendar.month_name[mes]

    # Filtrar mensajes del mes en cuestión si tienen fecha, o usar todos
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    if not user_msgs:
        return None

    resumen_conversaciones = "\n".join(f"- {m[:200]}" for m in user_msgs[-60:])

    prompt = f"""Eres Sofía, la psicóloga de Raúl. Tienes acceso a lo que te platicó durante {nombre_mes} {año}.

MENSAJES DEL USUARIO EN SESIONES PASADAS:
{resumen_conversaciones}

Genera un reporte mensual de progreso emocional. Incluye:
1. EMOCIONES DOMINANTES: ¿qué emociones aparecieron más?
2. PATRONES DETECTADOS: ¿qué comportamientos o pensamientos se repiten?
3. LO QUE MEJORÓ: avances reales que notas
4. LO QUE SIGUE PENDIENTE: áreas que necesitan trabajo
5. RECOMENDACIÓN PARA EL MES QUE SIGUE: una cosa concreta a trabajar

Tono: profesional, cálido, honesto. Máximo 20 líneas. Sin markdown. Habla directo a Raúl."""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def _generar_reporte_sofia_anual_sync(año=None) -> str:
    """Genera el análisis emocional anual de Sofía."""
    data = load_data()
    history = data.get("sofia_history", [])
    if not history:
        return None
    now = datetime.now(TIMEZONE)
    año = año or (now.year - 1)
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    if not user_msgs:
        return None
    resumen = "\n".join(f"- {m[:150]}" for m in user_msgs[-100:])
    prompt = f"""Eres Sofía, psicóloga de Raúl. Tienes el historial completo del año {año}.

MUESTRA DE LO QUE PLATICÓ RAÚL ESTE AÑO:
{resumen}

Genera un REPORTE ANUAL EMOCIONAL. Incluye:
1. CÓMO FUE EL AÑO: resumen de eventos emocionales clave
2. CÓMO REACCIONÓ: patrones de respuesta ante la adversidad
3. LO QUE MEJORÓ: crecimiento real
4. LO QUE SIGUE ARRASTRANDO: heridas o patrones no resueltos
5. SITUACIONES IMPORTANTES: momentos clave del año
6. VISIÓN QUE TE FALTÓ: qué perspectiva le habría ayudado a crecer más
7. REFLEXIÓN FINAL: algo que lo ayude a valorar lo que vivió

Máximo 30 líneas. Sin markdown. Tono: honesto, profundo, esperanzador."""
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def _generar_reporte_financiero_anual_sync(año=None) -> str:
    """Genera el análisis financiero anual."""
    now = datetime.now(TIMEZONE)
    año = año or (now.year - 1)
    data = load_data()

    import calendar

    resumen_meses = []
    for mes in range(1, 13):
        gastos   = get_gastos_mes(año, mes)
        ingresos = get_ingresos_mes(año, mes)
        movs     = get_movimientos_mes(año, mes)
        if not gastos and not ingresos:
            continue
        tg = sum(g["cantidad"] for g in gastos)
        ti = sum(i["cantidad"] for i in ingresos)
        bal = ti - tg
        nombre = calendar.month_abbr[mes]
        resumen_meses.append(f"{nombre}: ingresos=${ti:.0f} gastos=${tg:.0f} balance=${bal:+.0f}")

    if not resumen_meses:
        return None

    datos_str = "\n".join(resumen_meses)
    prompt = f"""Analiza las finanzas de Raúl en {año}.

DATOS POR MES:
{datos_str}

Genera un REPORTE FINANCIERO ANUAL. Incluye:
1. RESUMEN GENERAL: total ingresos, gastos, balance del año
2. DISTRIBUCIÓN DE CAPITAL: cómo se distribuyó el dinero
3. MEJORES Y PEORES MESES: con análisis de qué pasó
4. ERRORES Y ACIERTOS: decisiones financieras notables
5. RECOMENDACIONES: 3 cosas concretas para mejorar el manejo del dinero el siguiente año

Máximo 20 líneas. Sin markdown. Directo a Raúl, tono de coach financiero."""
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.5,
    )
    return resp.choices[0].message.content.strip()

