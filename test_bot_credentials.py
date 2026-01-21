import os
import requests

APP_ID = os.getenv("BOT_APP_ID")
APP_SECRET = os.getenv("BOT_APP_SECRET")
BOT_TENANT_ID = os.getenv("BOT_TENANT_ID")

if not APP_ID or not APP_SECRET or not BOT_TENANT_ID:
    print("❌ Faltan las variables BOT_APP_ID, BOT_APP_SECRET o BOT_TENANT_ID")
    exit(1)

print(f"🔍 Verificando credenciales para AppId={APP_ID} en tenant={BOT_TENANT_ID}")

# Paso 1️⃣ - Obtener el token OAuth2
token_url = f"https://login.microsoftonline.com/{BOT_TENANT_ID}/oauth2/v2.0/token"
token_data = {
    "grant_type": "client_credentials",
    "client_id": APP_ID,
    "client_secret": APP_SECRET,
    "scope": "https://api.botframework.com/.default",
}

token_resp = requests.post(token_url, data=token_data)

try:
    token_json = token_resp.json()
except Exception:
    token_json = None

if token_resp.status_code != 200:
    print("❌ Error obteniendo token (flujo como app.py)")
    print(f"Status: {token_resp.status_code}")
    print(f"Detalle: {token_resp.text}")
    exit(1)

if not isinstance(token_json, dict):
    print("❌ Respuesta inesperada: no es JSON")
    print(f"Body: {token_resp.text[:500]}")
    exit(1)

access_token = token_json.get("access_token")
if not access_token:
    print("❌ Respuesta OK pero no viene 'access_token'")
    print(f"Respuesta JSON: {token_json}")
    exit(1)

print("✅ Token obtenido correctamente.")

# Paso 2️⃣ - Probar acceso al endpoint del Bot Framework
# Este endpoint no envía mensaje real, pero valida si el token es aceptado.
# Usa un GET a /v3/conversations para comprobar autenticación.

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

print("🔍 Verificando autorización con el servicio de Bot Framework...")

test_url = "https://api.botframework.com/v3/conversations"
test_resp = requests.get(test_url, headers=headers)

if test_resp.status_code == 401:
    print("❌ Token rechazado por el servicio de Bot Framework (Unauthorized).")
    print("   👉 Revisa que el secreto coincida con el configurado en tu recurso Azure Bot.")
elif test_resp.status_code == 403:
    print("❌ Acceso prohibido (Forbidden). Puede que el App Registration no tenga permisos suficientes.")
elif test_resp.status_code in [200, 204, 404]:
    print("✅ Autenticación aceptada por el servicio de Bot Framework.")
    print(f"   Código devuelto: {test_resp.status_code}")
else:
    print("⚠️ Respuesta inesperada del servicio de Bot Framework.")
    print(f"Status: {test_resp.status_code}")
    print(f"Body: {test_resp.text[:500]}")
