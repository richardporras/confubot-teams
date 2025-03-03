import os
import requests
from flask import Flask, request, jsonify
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity, ActivityTypes

# 🔹 Cargar Secrets desde Variables de Entorno
BOT_APP_ID = os.getenv("BOT_APP_ID", "")  # ID del Bot en Azure
BOT_APP_SECRET = os.getenv("BOT_APP_SECRET", "")  # Secreto del Bot en Azure
AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")  # Nombre del servicio de búsqueda
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")  # Clave de API de Azure Search
INDEX_NAME = "confluence-index"  # Índice de Azure Cognitive Search

# 🔹 Verificar que todas las variables están configuradas
if not AZURE_SEARCH_SERVICE or not AZURE_SEARCH_API_KEY:
    raise ValueError("❌ ERROR: Faltan variables de entorno necesarias para Azure Search")

# 🔹 Crear Flask App
app = Flask(__name__)

# 🔹 Configurar BotFrameworkAdapter (para futuras mejoras)
settings = BotFrameworkAdapterSettings(BOT_APP_ID, BOT_APP_SECRET)
bot_adapter = BotFrameworkAdapter(settings)

def search_azure(query):
    """🔍 Realiza una búsqueda en Azure Cognitive Search"""
    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_API_KEY
    }

    payload = {
        "search": query,  # 🔹 Texto de búsqueda ingresado por el usuario
        "top": 5,  # 🔹 Máximo de resultados
        "select": "title,content,url"  # 🔹 Campos a devolver
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        return response.json().get("value", [])
    else:
        print(f"⚠️ Error en la búsqueda: {response.status_code} - {response.text}")
        return []

@app.route("/api/messages", methods=["POST"])
def messages():
    """📨 Maneja los mensajes entrantes en Microsoft Teams"""
    body = request.json
    if not body or "text" not in body:
        return jsonify({"status": "No se recibió un mensaje válido"})

    user_query = body["text"]  # 🔹 Captura la consulta del usuario
    search_results = search_azure(user_query)  # 🔹 Realiza la búsqueda en Azure

    if search_results:
        message = "**🔍 Resultados de Confluence:**\n\n"
        for doc in search_results:
            message += f"- **[{doc['title']}]({doc['url']})**\n"
        response_text = message
    else:
        response_text = "⚠️ No encontré información relevante en Confluence."

    # 🔹 Crear respuesta en Teams
    activity = Activity(type=ActivityTypes.message, text=response_text)
    return jsonify(activity.serialize())  # 🔹 Convertir la respuesta en JSON válido

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3978))  # Usar puerto definido en Azure o 3978 por defecto
    app.run(host="0.0.0.0", port=port, debug=True)
