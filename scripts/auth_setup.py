import os.path
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Determine the project root (one level up from this script)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar"
]

def main():
    """Muestra el flujo de autorizaci\u00f3n OAuth2 b\u00e1sico y guarda el token.
    Este script debe ejecutarse localmente ANTES de arrancar el contenedor Docker.
    Mapearemos 'token.json' dentro del docker-compose posteriormente.
    """
    creds = None
    
    # El archivo token.json almacena los tokens de acceso y refresco del usuario.
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
    # Si no hay credenciales (o son inv\u00e1lidas), forzamos al usuario a loguearse.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                print("==================================================")
                print(f"\u274c ERROR: No se encuentra el archivo {CREDENTIALS_PATH}")
                print("Descarga tu 'credentials.json' desde la consola de Google Cloud")
                print("y col\u00f3calo en la RA\u00cdZ del proyecto antes de continuar.")
                print("==================================================")
                return
            
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
            
        # Guarda las credenciales generadas para futuras ejecuciones del agente.
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
            print(f"\u2705 \u00c9xito! Tu token.json ha sido generado en: {TOKEN_PATH}")

if __name__ == "__main__":
    main()
