import os
import requests
from flask import Flask, request, jsonify
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
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
INDEX_NAME = "confluence-index"

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
        "top": 5,
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
    user_query = body.get("text") or (body.get("activity", {}).get("text"))

    if not user_query:
        return jsonify({"status": "No se recibió un mensaje válido"}), 400

    # Manejar excepciones en la búsqueda de Azure
    try:
        search_results = search_azure(user_query)
    except Exception as e:
        search_results = []
        print(f"⚠️ Error en Azure Search: {e}")

    if search_results:
        message = "**🔍 Resultados de Confluence:**\n\n"
        for doc in search_results:
            message += f"- **[{doc['title']}]({doc['url']})**\n"
        response_text = message
    else:
        response_text = "⚠️ No encontré información relevante en Confluence."

    # Crear respuesta en formato Microsoft Teams
    activity = Activity(type=ActivityTypes.message, text=response_text)

    # Obtener correctamente la referencia de la conversación
    conversation_reference = TurnContext.get_conversation_reference(activity)  # ✅ CORREGIDO

    # Asignar correctamente los valores de la conversación
    activity.from_property = conversation_reference.user
    activity.recipient = conversation_reference.bot
    activity.conversation = conversation_reference.conversation

    return jsonify(activity.serialize()), 200

# 🔹 Iniciar la aplicación en el puerto asignado por Azure
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
