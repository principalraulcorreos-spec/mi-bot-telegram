# -*- coding: utf-8 -*-
"""
Script de autenticacion Google Fit — correr UNA VEZ.

Uso:
  python fit_auth.py

Abre el navegador. Inicia sesion con la misma cuenta de Google
que usas para Calendar y Gmail en el bot.
Al terminar imprime el GOOGLE_FIT_REFRESH_TOKEN para Railway.
"""
import json, sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/fitness.activity.read',
    'https://www.googleapis.com/auth/fitness.body.read',
]

def main():
    print("=" * 50)
    print("AUTENTICACION GOOGLE FIT PARA EL BOT")
    print("Samsung Galaxy Watch 7 -> Google Fit -> Bot")
    print("=" * 50)

    try:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    except FileNotFoundError:
        print("\nERROR: No se encontro credentials.json")
        print("Asegurate de correr este script desde la carpeta telegram-bot/")
        sys.exit(1)

    print("\nAbriendo navegador...")
    print("Inicia sesion con TU cuenta principal de Google.\n")

    creds = flow.run_local_server(
        port=8080, open_browser=True, timeout_seconds=120,
        authorization_prompt_message="Abriendo navegador...",
        prompt='consent'
    )

    print("\n" + "=" * 50)
    print("REFRESH TOKEN para Google Fit:")
    print("=" * 50)
    print(creds.refresh_token)
    print("=" * 50)
    print()
    print("Agrega esto en Railway como variable de entorno:")
    print(f"  GOOGLE_FIT_REFRESH_TOKEN={creds.refresh_token}")
    print()
    print("El bot sincronizara pasos y calorias automaticamente cada noche a las 10pm.")

    with open("fit_token.json", "w") as f:
        json.dump({"refresh_token": creds.refresh_token}, f, indent=2)
    print("\nGuardado en fit_token.json (no subir a git)")

if __name__ == "__main__":
    main()
