import os
import requests
import logging
import re
from flask import Flask, request, jsonify
from botbuilder.schema import Activity, ActivityTypes

# 🔹 Configuración de logs para depuración
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# 🔹 Configuración de Azure Cognitive Search
AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
INDEX_NAME = "confluence-index"

# 🔹 Configuración de Azure OpenAI
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")  # URL de Azure OpenAI
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")  # Clave API
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")  # Nombre del deployment

def preprocess_query_for_search(query):
    """🔍 Optimiza la query antes de enviarla a Azure Cognitive Search."""
    
    # 🔹 Convertimos la pregunta a minúsculas
    query = query.lower()
    
    # 🔹 Eliminamos palabras irrelevantes para la búsqueda
    stopwords = ["cuál", "cuáles", "cómo", "puedo", "sería", "son", "el", "la", "los", "las", "de", "en", "para"]
    words = query.split()
    filtered_words = [word for word in words if word not in stopwords]
    
    # 🔹 Eliminamos signos de puntuación
    clean_query = re.sub(r"[^\w\s]", "", " ".join(filtered_words))
    
    logging.info(f"🔍 Query original: {query} → Query optimizada: {clean_query}")
    return clean_query

def search_azure(query):
    """🔍 Mejora la búsqueda en Azure Cognitive Search para incluir más términos y mejores resultados."""
    optimized_query = preprocess_query_for_search(query)  # 🔹 Optimizamos la query antes de enviarla

    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_SEARCH_API_KEY}
    
    payload = {
        "search": optimized_query,  # 🔹 Usamos la query optimizada
        "queryType": "semantic",
        "searchFields": "title,content",
        "top": 10,
        "select": "title,content,url",
        "filter": "length(content) gt 0"
    }

    logging.info(f"🔍 Enviando consulta mejorada a Azure Search: {payload}")

    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()
    
    logging.info(f"📩 Resultados de Azure Search: {response_data}")

    if response.status_code == 200:
        return response_data.get("value", [])
    return []

def generate_response(query, search_results):
    """🧠 Usa Azure OpenAI para generar una respuesta con información de Confluence y el enlace al documento relevante."""
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_API_KEY}

    if search_results:
        # 🔹 Seleccionamos el primer documento como referencia principal
        best_document = search_results[0]
        best_title = best_document["title"]
        best_content = best_document["content"][:2000]  # 🔹 Limitamos a 2000 caracteres
        best_url = best_document["url"]

        # 🔹 Creamos el contexto para OpenAI
        context = "\n\n".join([f"- **{doc['title']}**: {doc['content'][:1000]}" for doc in search_results])
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
    """📩 Maneja mensajes recibidos en Microsoft Teams."""
    body = request.json
    user_query = body.get("text")

    if not user_query:
        return jsonify({"status": "No se recibió un mensaje válido"}), 400

    search_results = search_azure(user_query)
    response_text = generate_response(user_query, search_results)

    activity = Activity(type=ActivityTypes.message, text=response_text)
    return jsonify(activity.serialize()), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
