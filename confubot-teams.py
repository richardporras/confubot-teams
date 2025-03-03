import os
import requests
from flask import Flask, request, jsonify

# Crear Flask App
app = Flask(__name__)

# 🔹 Endpoint de Health Check
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200

# 🔹 Endpoint raíz (para verificar conexión)
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot is running on Azure!", 200

# 🔹 Endpoint principal del bot
@app.route("/api/messages", methods=["POST"])
def messages():
    """Maneja mensajes recibidos por el bot en Teams."""
    body = request.json
    if not body or "text" not in body:
        return jsonify({"status": "No se recibió un mensaje válido"})

    user_query = body["text"]
    response_text = f"✅ Recibí tu mensaje: {user_query}"

    return jsonify({"type": "message", "text": response_text})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Azure asigna un puerto dinámico
    app.run(host="0.0.0.0", port=port, debug=True)
