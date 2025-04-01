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

# 🔹 Prompts
PROMPT_BASE = "Eres un asistente técnico experto en documentación interna de Confluence."
INTENT_PROMPTS = {
    "resumen": "Resume la información proporcionada de manera clara, concisa y útil.",
    "extraccion": "Extrae datos clave y listados relevantes de la siguiente información.",
    "consulta_directa": "Responde de forma precisa usando solo la información proporcionada."
}

async def on_message_activity(turn_context: TurnContext):
    user_query = turn_context.activity.text.strip()
    logging.info(f"🔍 Usuario pregunta: {user_query}")

    intent = detect_intent(user_query)
    logging.info(f"🔍 Intención detectada: {intent}")

    search_results = search_azure(user_query)
    response_text = generate_response_by_intent(user_query, search_results, intent)

    logging.info(f"🤖 Respuesta del bot: {response_text}")
    await turn_context.send_activity(Activity(type=ActivityTypes.message, text=response_text))

def detect_intent(query):
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_API_KEY}
    messages = [
        {"role": "system", "content": "Clasifica esta consulta como 'resumen', 'extraccion' o 'consulta_directa'. Solo responde con una de esas palabras."},
        {"role": "user", "content": query}
    ]
    payload = {"messages": messages, "temperature": 0, "max_tokens": 10}
    response = requests.post(url, headers=headers, json=payload)
    return response.json().get("choices", [{}])[0].get("message", {}).get("content", "consulta_directa").strip().lower()

def search_azure(query):
    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_SEARCH_API_KEY}
    payload = {"search": query, "top": 5, "select": "title,content,url"}
    
    response = requests.post(url, headers=headers, json=payload)
    
    if not response.ok:
        return []

    # 🔹 Filtrar por umbral mínimo de score
    min_score_threshold = float(os.getenv("MIN_SCORE_THRESHOLD", 10))
    results = response.json().get("value", [])
    return [doc for doc in results if doc.get("@search.score", 0) >= min_score_threshold]


def build_context(search_results):
    return "\n\n".join(
        [f"- **{doc.get('title', 'Documento sin título')}**: {doc.get('content', '')[:10000]}"
         for doc in search_results]
    )

def generate_openai_response(query, context, intent):
    instruction = f"{PROMPT_BASE} {INTENT_PROMPTS.get(intent, INTENT_PROMPTS['consulta_directa'])}"
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_API_KEY}
    messages = [
        {"role": "system", "content": instruction},
        {"role": "assistant", "content": context},
        {"role": "user", "content": f"Pregunta: {query}"}
    ]
    payload = {"messages": messages, "temperature": 0.2, "max_tokens": 900}
    response = requests.post(url, headers=headers, json=payload)
    return response.json().get("choices", [{}])[0].get("message", {}).get("content", "No encontré información relevante.")

def generate_response_by_intent(query, search_results, intent):
    context = build_context(search_results)
    response = generate_openai_response(query, context, intent)

    # 🔹 Recoger hasta 3 URLs únicas con su score
    seen_urls = set()
    enlaces = []
    for doc in search_results:
        url = doc.get("url", "")
        score = doc.get("@search.score", 0.0)
        if url and url not in seen_urls:
            seen_urls.add(url)
            title = doc.get("title", "Documento sin título")
            enlaces.append(f"🔗 [{title}]({url}) (score: {score:.2f})")
        if len(enlaces) == 3:
            break

    if enlaces:
        response += "\n\n" + "\n\n".join(enlaces)

    return response


@app.route("/api/messages", methods=["POST"])
async def messages():
    try:
        body = await request.get_json()
        logging.info(f"📩 Petición recibida: {body}")

        auth_header = request.headers.get("Authorization", "")
        activity = Activity().deserialize(body)

        async def aux_func(turn_context: TurnContext):
            try:
                if turn_context.activity.type == ActivityTypes.message and turn_context.activity.text:
                    await on_message_activity(turn_context)
                else:
                    logging.info("🔹 Ignorando mensaje sin texto.")
            except Exception as e:
                logging.error(f"❌ Error procesando mensaje del usuario: {e}", exc_info=True)
                await turn_context.send_activity(
                    Activity(type=ActivityTypes.message, text="Se ha producido un error procesando tu mensaje.")
                )

        await adapter.process_activity(activity, auth_header, aux_func)
        return Response(status=201)

    except PermissionError as e:
        logging.warning(f"🔐 Acceso no autorizado: {e}")
        return Response("Unauthorized", status=401)

    except Exception as e:
        logging.error(f"❌ Error general en la ruta /api/messages: {e}", exc_info=True)
        return Response("Internal Server Error", status=500)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
