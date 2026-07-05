# Manual de instalación y configuración

Bot de Telegram tipo "coach de vida": registra gastos/ingresos, hábitos,
trades, salud (pasos/calorías/peso), notas y recordatorios; te manda reportes
semanales/mensuales/anuales; y tiene un asistente de IA (Groq) que entiende
lenguaje natural, transcribe notas de voz y lee fotos de recibos.

Este manual asume que **no sabes programar** pero puedes copiar/pegar
comandos y seguir instrucciones paso a paso. Se tarda entre 20 y 40 minutos
la primera vez.

---

## 1. Qué necesitas antes de empezar (todo gratis)

| Cuenta | Para qué | Link |
|---|---|---|
| Telegram | Crear tu bot | ya la tienes |
| GitHub | Guardar el código | https://github.com |
| Render (o Railway) | Correr el bot 24/7 | https://render.com |
| Supabase | Guardar tus datos de forma permanente | https://supabase.com |
| Groq | El cerebro de IA del bot (gratis con límites generosos) | https://console.groq.com |
| Google Cloud (opcional) | Solo si quieres Calendar/Gmail automáticos | https://console.cloud.google.com |

---

## 2. Crear tu bot de Telegram

1. Abre Telegram y busca **@BotFather**.
2. Envíale `/newbot`, ponle un nombre y un username (debe terminar en `bot`).
3. Te va a dar un **token** parecido a `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   Guárdalo, es tu `BOT_TOKEN`.

---

## 3. Subir el código a tu propio GitHub

1. Crea una cuenta en GitHub si no tienes.
2. Crea un repositorio nuevo (puede ser privado), por ejemplo `mi-bot-telegram`.
3. Descomprime el zip que te compartieron en una carpeta.
4. Sube el contenido a tu repo (con GitHub Desktop, o con estos comandos en
   la carpeta del proyecto):
   ```
   git init
   git add .
   git commit -m "Bot inicial"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/mi-bot-telegram.git
   git push -u origin main
   ```

> El `.gitignore` ya excluye archivos sensibles (`.env`, `credentials.json`,
> `registro.json`, tokens de Gmail) — no se suben por accidente.

---

## 4. Crear la base de datos en Supabase (gratis, evita perder tus datos)

Sin esto, si tu hosting reinicia el servicio (pasa seguido en los planes
gratis), **pierdes todo lo registrado**. Con Supabase, tus datos quedan
guardados de forma permanente.

1. Crea una cuenta/proyecto en https://supabase.com (elige la región más
   cercana a ti).
2. Ve a **SQL Editor** (menú izquierdo) → **New query** y pega:
   ```sql
   create table bot_data (id int primary key, data jsonb);
   insert into bot_data (id, data) values (1, '{}');
   ```
   Dale a **Run**.
3. Ve a **Settings → API**. Copia:
   - **Project URL** → esta es tu `SUPABASE_URL`
   - **service_role secret key** (no la "anon public") → esta es tu `SUPABASE_KEY`

---

## 5. Crear tu API key de Groq (el "cerebro" de IA)

1. Entra a https://console.groq.com y crea una cuenta.
2. Ve a **API Keys → Create API Key**.
3. Copia la key generada → esta es tu `GROQ_API_KEY`.

---

## 6. (Opcional) Google Calendar y Gmail automáticos

Si NO quieres que el bot lea tu agenda de Google ni detecte transacciones de
tus correos, **sáltate este paso** — el bot funciona perfecto sin esto, solo
no tendrás esas dos funciones extra.

1. Ve a https://console.cloud.google.com y crea un proyecto nuevo.
2. En **APIs & Services → Library**, activa:
   - Google Calendar API
   - Gmail API
3. En **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Tipo de aplicación: **Aplicación de escritorio**
   - Descarga el archivo JSON y renómbralo a `credentials.json`, ponlo en la
     carpeta del proyecto.
4. En tu computadora (con Python instalado), dentro de la carpeta del
   proyecto:
   ```
   pip install -r requirements.txt
   python gmail_auth.py
   ```
   Te va a pedir iniciar sesión con la cuenta de Gmail que quieras conectar
   (puedes repetirlo para una segunda cuenta). Al final te imprime:
   - `GMAIL_CLIENT_ID`
   - `GMAIL_CLIENT_SECRET`
   - `GMAIL_REFRESH_TOKEN_1` (o `_2` si es la segunda cuenta)

   Guarda esos tres valores, son variables de entorno que agregarás en el
   paso 8.

---

## 7. Personalizar el bot a TU vida (`config.py`)

Abre `config.py` — es el único archivo que necesitas tocar para adaptar el
bot a ti. Ahí puedes cambiar:

- `PRESUPUESTO` — tus categorías de gasto y su límite mensual.
- `CATEGORIAS_ALIAS` — palabras que el bot reconoce y a qué categoría las
  manda (ej. "uber" → transporte).
- `HABITOS` — la lista de hábitos diarios que quieres trackear.
- `RUTINA_LMV` — tu rutina de ejercicio.
- `META_PASOS_DIARIO` — tu meta diaria de pasos.
- `FRASES_RAW` — las frases motivacionales que te manda el bot.
- `PREGUNTAS_SEMANAL` / `PREGUNTAS_MENSUAL` — las preguntas de reflexión.
- `CAPITAL`, `PEDIR_INFORME`, `ENVIAR_INFORME` — mensajes de texto fijos
  (edítalos o bórralos si no aplican a tu situación).

No hace falta tocar ningún otro archivo `.py` para personalizar el bot.

---

## 8. Desplegar en Render (gratis, 24/7)

1. Crea una cuenta en https://render.com y conecta tu cuenta de GitHub.
2. **New → Background Worker** → selecciona tu repositorio.
3. Configuración:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. En la sección **Environment**, agrega las variables (una por una, con
   "Add Environment Variable"):

   | Variable | Valor |
   |---|---|
   | `BOT_TOKEN` | el token de BotFather (paso 2) |
   | `SUPABASE_URL` | de Supabase (paso 4) |
   | `SUPABASE_KEY` | de Supabase (paso 4) |
   | `GROQ_API_KEY` | de Groq (paso 5) |
   | `GMAIL_CLIENT_ID` | solo si hiciste el paso 6 |
   | `GMAIL_CLIENT_SECRET` | solo si hiciste el paso 6 |
   | `GMAIL_REFRESH_TOKEN_1` | solo si hiciste el paso 6 |
   | `GMAIL_REFRESH_TOKEN_2` | solo si conectaste una segunda cuenta Gmail |

5. Dale a **Create Background Worker**. Render va a instalar todo y arrancar
   el bot solo — revisa la pestaña **Logs**, debe decir
   `Bot iniciado. Esperando mensajes...`.

---

## 9. Primer uso

1. Abre tu bot en Telegram y manda `/start`.
2. Eso guarda tu `chat_id` automáticamente — a partir de ahí el bot ya sabe
   a quién mandarte los reportes y avisos programados.
3. Explora el menú con `/menu`.

---

## 10. Actualizar el bot en el futuro

Cada vez que cambies algo en `config.py` (o cualquier archivo) y quieras que
se refleje en producción:
```
git add .
git commit -m "Ajusto mi configuración"
git push
```
Render vuelve a desplegar automáticamente en 1-2 minutos.

---

## 11. Estructura del proyecto (por si quieres entender/modificar más)

| Archivo | Qué contiene |
|---|---|
| `config.py` | **Personalización** — presupuesto, hábitos, frases, preguntas |
| `utils.py` | Funciones auxiliares (texto, fechas) |
| `storage.py` | Guardar/leer datos (Supabase o archivo local) |
| `domain.py` | Lógica de negocio: registrar gastos, hábitos, trades, salud |
| `keyboards.py` | Botones de Telegram |
| `ai_service.py` | Todo lo relacionado a IA (Groq): chat, voz, fotos, reportes narrados |
| `calendar_service.py` | Integración con Google Calendar |
| `gmail_service.py` | Detección automática de transacciones en Gmail |
| `forex_service.py` | Noticias de forex |
| `reports.py` | Generación de reportes y resúmenes |
| `bot.py` | Comandos, botones, jobs programados y arranque del bot |

---

## 12. Problemas comunes

- **El bot no responde nada**: revisa los logs de Render, casi siempre es un
  `BOT_TOKEN` mal copiado o una variable de entorno faltante.
- **Se te "olvidan" los datos después de un rato**: te faltó configurar
  `SUPABASE_URL`/`SUPABASE_KEY` (paso 4) — sin eso, Render borra los datos en
  cada reinicio.
- **La IA no responde / da error**: revisa que `GROQ_API_KEY` esté bien
  copiada y que tu cuenta de Groq siga activa.
- **Gmail/Calendar no funcionan**: son opcionales; si no configuraste el
  paso 6 completo, el bot simplemente no ofrece esas funciones (no rompe
  nada más).
