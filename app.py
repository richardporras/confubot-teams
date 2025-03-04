import os
import requests
from flask import Flask, request, jsonify

# Crear Flask App
app = Flask(__name__)

# 🔹 Endpoint de Health Check para Azure App Service
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200

# 🔹 Endpoint raíz (para verificar conexión)
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot is running on Azure!", 200

# 🔹 Configuración de Azure Cognitive Search
AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
INDEX_NAME = "confluence-arq"

if not AZURE_SEARCH_SERVICE or not AZURE_SEARCH_API_KEY:
    raise ValueError("❌ ERROR: Missing environment variables for Azure Search")

# 🔹 Función para buscar en Azure Cognitive Search
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

# 🔹 Endpoint principal del bot
@app.route("/api/messages", methods=["POST"])
def messages():
    body = request.json
    if not body or "text" not in body:
        return jsonify({"status": "No valid message received"})

    user_query = body["text"]
    search_results = search_azure(user_query)

    if search_results:
        message = "**🔍 Search Results from Confluence:**\n\n"
        for doc in search_results:
            message += f"- **[{doc['title']}]({doc['url']})**\n"
        response_text = message
    else:
        response_text = "⚠️ No relevant information found in Confluence."

    return jsonify({"type": "message", "text": response_text})

# 🔹 Ejecutar la app en Azure con el puerto asignado
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Azure assigns a dynamic port
    app.run(host="0.0.0.0", port=port, debug=True)
