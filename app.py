import os
import requests
from flask import Flask, request, jsonify
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity, ActivityTypes

# 🔹 Configurar Flask App
app = Flask(__name__)

# 🔹 Configurar credenciales del bot en Microsoft Teams
BOT_APP_ID = os.getenv("BOT_APP_ID", "")
BOT_APP_SECRET = os.getenv("BOT_APP_SECRET", "")

# 🔹 Configurar el adaptador de Microsoft Bot Framework
settings = BotFrameworkAdapterSettings(BOT_APP_ID, BOT_APP_SECRET)
bot_adapter = BotFrameworkAdapter(settings)

# 🔹 Configuración de Azure Cognitive Search
AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
INDEX_NAME = "confluence-index"  # Nombre del índice en Azure Search

if not AZURE_SEARCH_SERVICE or not AZURE_SEARCH_API_KEY:
    raise ValueError("❌ ERROR: Faltan variables de entorno necesarias para Azure Search")

# 🔹 Endpoint de Health Check (para evitar errores 503 en Azure)
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200

# 🔹 Endpoint raíz (para verificar conexión rápida)
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot is running on Azure!", 200

# 🔹 Función para buscar información en Azure Cognitive Search
def search_azure(query):
    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_API_KEY
    }
    payload = {
        "search": query,
        "top": 5,  # Número máximo de resultados
        "select": "title,content,url"
    }
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        return response.json().get("value", [])
    else:
        return []

# 🔹 Endpoint del bot para recibir mensajes desde Teams
@app.route("/api/messages", methods=["POST"])
def messages():
    """Maneja mensajes recibidos en Microsoft Teams"""
    body = request.json
    if not body or "text" not in body:
        return jsonify({"status": "No se recibió un mensaje válido"})

    user_query = body["text"]  # Captura la consulta del usuario
    search_results = search_azure(user_query)  # Realiza la búsqueda en Azure Search

    if search_results:
        message = "**🔍 Resultados de Confluence:**\n\n"
        for doc in search_results:
            message += f"- **[{doc['title']}]({doc['url']})**\n"
        response_text = message
    else:
        response_text = "⚠️ No encontré información relevante en Confluence."

    # Crear respuesta para Microsoft Teams
    activity = Activity(type=ActivityTypes.message, text=response_text)
    return jsonify(activity.serialize())

# 🔹 Iniciar la aplicación en el puerto asignado por Azure
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Azure asigna un puerto dinámico
    app.run(host="0.0.0.0", port=port, debug=True)
