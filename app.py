import os
import requests
import logging
from flask import Flask, request, jsonify
from botbuilder.schema import Activity, ActivityTypes

# 🔹 Habilitar logging para depuración detallada
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# 🔹 Configuración de Azure Cognitive Search
AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX")

# 🔹 Configuración de Azure OpenAI
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")  # URL de Azure OpenAI
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")  # Clave API
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")  # Nombre del deployment

def search_azure(query):
    """🔍 Busca información en Azure Cognitive Search."""
    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_SEARCH_API_KEY}
    payload = {"search": query, "top": 5, "select": "title,content,url"}

    logging.info(f"🔍 Enviando consulta a Azure Search: {payload}")

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        results = response.json().get("value", [])
        logging.info(f"📩 Resultados de Azure Search: {len(results)} documentos encontrados")
        return results
    
    logging.error(f"❌ Error en Azure Search: {response.status_code} - {response.text}")
    return []

def generate_response(query, search_results):
    """🧠 Usa Azure OpenAI para generar una respuesta con información de Confluence y el enlace al documento relevante."""
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_API_KEY}

    if search_results:
        # 🔹 Seleccionamos el primer documento como referencia principal
        best_document = search_results[0]
        best_title = best_document.get("title", "Documento sin título")
        best_content = best_document.get("content", "")[:2000]
        best_url = best_document.get("url", "")

        # 🔹 Creamos el contexto para OpenAI
        context = "\n\n".join([f"- **{doc.get('title', 'Documento sin título')}**: {doc.get('content', '')[:2000]}" for doc in search_results])
        context_prompt = f"""Estos son los documentos relevantes de Confluence:

        {context}

        Usa esta información para responder a la siguiente pregunta de la manera más precisa posible."""
    else:
        best_url = None
        best_title = "No se encontraron documentos relevantes"
        context_prompt = "No se encontraron documentos en Confluence, intenta responder lo mejor posible."

    messages = [
        {"role": "system", "content": "Eres un asistente técnico experto en documentación interna de Confluence."},
        {"role": "assistant", "content": context_prompt},
        {"role": "user", "content": f"Pregunta: {query}"}
    ]

    payload = {"messages": messages, "temperature": 0.2, "max_tokens": 900}

    logging.info(f"📩 Enviando consulta a Azure OpenAI: {payload}")
    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()
    logging.info(f"📩 Respuesta de OpenAI: {response_data}")

    response_text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "No encontré información relevante.")

    # 🔹 Incluir el enlace al documento más relevante en la respuesta
    if best_url:
        response_text += f"\n\n🔗 [Consulta más detalles en Confluence: {best_title}]({best_url})"

    return response_text


@app.route("/api/messages", methods=["POST"])
def messages():
    """📩 Maneja mensajes recibidos desde WebChat."""
    
    # 🔹 Loggear la petición completa
    logging.info(f"📩 Petición recibida: {request.method} {request.url}")
    logging.info(f"🔍 Cabeceras: {dict(request.headers)}")

    try:
        # 🔹 Loggear el cuerpo de la petición
        body = request.get_json()
        logging.info(f"📩 Cuerpo de la petición: {body}")

        # 🔹 Ignorar mensajes de inicio de conversación en WebChat
        if body.get("type") == "conversationUpdate":
            logging.info("🔹 Mensaje de tipo 'conversationUpdate' recibido. No se requiere respuesta.")
            return jsonify({"status": "Conversación iniciada"}), 200

        # 🔹 Asegurar que es un mensaje de usuario
        if body.get("type") != "message":
            logging.error(f"❌ Error: Tipo de mensaje no válido ({body.get('type')}).")
            return jsonify({"error": "Tipo de mensaje no válido"}), 400

        user_query = body.get("text", "").strip()
        if not user_query:
            logging.error("❌ Error: El mensaje está vacío.")
            return jsonify({"error": "Mensaje vacío"}), 400

        # 🔹 Buscar en Azure Cognitive Search
        search_results = search_azure(user_query)
        response_text = generate_response(user_query, search_results)

        # 🔹 Asegurar que "replyToId" y "serviceUrl" estén en la respuesta
        activity = {
            "type": "message",
            "text": response_text,
            "from": {"id": "bot"},
            "recipient": {"id": body["from"]["id"]},
            "replyToId": body.get("id"),
            "serviceUrl": body.get("serviceUrl")  # 🔹 Agregar el serviceUrl de la petición
        }

        logging.info(f"✅ Respuesta enviada: {activity}")
        return jsonify(activity), 200

    except Exception as e:
        logging.error(f"❌ Error procesando la petición: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
