import os
import requests
import logging
from quart import Quart, request, jsonify, Response
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes

# 🔹 Habilitar logging
logging.basicConfig(level=logging.INFO)

# 🔹 Quart App
app = Quart(__name__)

# 🔹 Azure Cognitive Search config
AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX")

# 🔹 Azure OpenAI config
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# 🔹 Bot Adapter Settings
adapter_settings = BotFrameworkAdapterSettings(
    app_id=os.getenv("BOT_APP_ID"), app_password=os.getenv("BOT_APP_SECRET")
)
adapter = BotFrameworkAdapter(adapter_settings)

async def on_message_activity(turn_context: TurnContext):
    user_query = turn_context.activity.text.strip()

    logging.info(f"🔍 Usuario pregunta: {user_query}")

    search_results = search_azure(user_query)
    response_text = generate_response(user_query, search_results)

    logging.info(f"🤖 Respuesta del bot: {response_text}")

    await turn_context.send_activity(
        Activity(type=ActivityTypes.message, text=response_text)
    )

def search_azure(query):
    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_SEARCH_API_KEY}
    payload = {"search": query, "top": 5, "select": "title,content,url"}

    response = requests.post(url, headers=headers, json=payload)
    return response.json().get("value", []) if response.ok else []

def generate_response(query, search_results):
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_API_KEY}

    context = "\n\n".join(
        [f"- **{doc.get('title', 'Documento sin título')}**: {doc.get('content', '')[:10000]}"
         for doc in search_results]
    )

    context_prompt = (
        "Estos son los documentos relevantes de Confluence:\n\n"
        f"{context}\n\n"
        "Usa esta información para responder a la siguiente pregunta de forma precisa."
        if search_results else
        "No se encontraron documentos relevantes. Intenta responder lo mejor posible."
    )

    messages = [
        {"role": "system", "content": "Eres un asistente técnico experto en documentación interna."},
        {"role": "assistant", "content": context_prompt},
        {"role": "user", "content": f"Pregunta: {query}"}
    ]

    payload = {"messages": messages, "temperature": 0.2, "max_tokens": 900}

    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()

    response_text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "No encontré información relevante.")

    if search_results:
        best_document = search_results[0]
        best_title = best_document.get("title", "Documento sin título")
        best_url = best_document.get("url", "")
        response_text += f"\n\n🔗 [Más detalles en Confluence: {best_title}]({best_url})"

    return response_text

@app.route("/api/messages", methods=["POST"])
async def messages():
    body = await request.get_json()
    logging.info(f"📩 Petición recibida: {body}")

    auth_header = request.headers.get("Authorization", "")
    activity = Activity().deserialize(body)

    async def aux_func(turn_context: TurnContext):
        if turn_context.activity.type == ActivityTypes.message and turn_context.activity.text:
            await on_message_activity(turn_context)
        else:
            logging.info("🔹 Ignorando mensaje sin texto.")

    await adapter.process_activity(activity, auth_header, aux_func)

    return Response(status=201)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)