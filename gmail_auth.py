# -*- coding: utf-8 -*-
"""
Script de autenticacion Gmail — correr UNA VEZ por cuenta.

Uso:
  python gmail_auth.py

Requiere credentials.json descargado de Google Cloud Console.
Abre el navegador para autorizar. Al terminar imprime el refresh_token.
"""

import json
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    print("=" * 50)
    print("AUTENTICACION GMAIL PARA EL BOT")
    print("=" * 50)
    print()
    cuenta = input("¿Cuál cuenta estás autorizando? (1=principal, 2=secundaria): ").strip()

    try:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    except FileNotFoundError:
        print("\nERROR: No se encontró credentials.json")
        print("Descárgalo de Google Cloud Console → APIs & Services → Credentials")
        sys.exit(1)

    print("\nAbriendo navegador para autorizar...")
    print("Inicia sesión con la cuenta correcta.\n")

    creds = flow.run_local_server(port=0)

    print("\n" + "=" * 50)
    print(f"REFRESH TOKEN para cuenta {cuenta}:")
    print("=" * 50)
    print(creds.refresh_token)
    print("=" * 50)
    print()
    print(f"Copia este token y agrégalo en Railway como:")
    if cuenta == "1":
        print(f"  GMAIL_REFRESH_TOKEN_1={creds.refresh_token}")
    else:
        print(f"  GMAIL_REFRESH_TOKEN_2={creds.refresh_token}")
    print()
    print("También necesitas agregar:")
    print("  GMAIL_CLIENT_ID=<tu client_id de credentials.json>")
    print("  GMAIL_CLIENT_SECRET=<tu client_secret de credentials.json>")
    print()

    # También guardar en archivo por si acaso
    output = {
        "cuenta": cuenta,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }
    filename = f"gmail_token_{cuenta}.json"
    with open(filename, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Guardado también en {filename} (no subir a git)")

if __name__ == "__main__":
    main()
