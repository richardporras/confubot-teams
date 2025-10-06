import os
import requests
import logging
from functools import wraps
import base64
import time
from typing import Dict, List

from quart import Quart, request, jsonify, Response
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes
import jwt
from botframework.connector.auth import MicrosoftAppCredentials


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

USERNAME = os.getenv("BASIC_AUTH_USER", "admin")
PASSWORD = os.getenv("BASIC_AUTH_PASS", "password")

# 🔹 Credenciales personalizadas que fuerzan el uso del tenant corporativo
class TenantAwareAppCredentials(MicrosoftAppCredentials):
    def __init__(self, app_id: str, password: str, tenant_id: str):
        # Llamamos al init original
        super().__init__(app_id, password)

        # Guardamos nuestros propios atributos
        self.app_id = app_id
        self.password = password
        self.tenant_id = tenant_id

        # 🔧 Forzamos el endpoint a nuestro tenant, no al global botframework.com
        self.oauth_endpoint = f"https://login.microsoftonline.com/{tenant_id}"
        self.oauth_scope = "https://api.botframework.com/.default"


        logging.info(f"🔐 Usando endpoint OAuth: {self.oauth_endpoint}")

    def get_access_token(self):
        token = super().get_access_token()
        logging.info(f"🪪 Token obtenido desde: {self.oauth_endpoint}")
        return token

BOT_APP_ID = os.getenv("BOT_APP_ID")
BOT_APP_SECRET= os.getenv("BOT_APP_SECRET")
TENANT_ID = os.getenv("BOT_TENANT_ID")

# 🔹 Bot Adapter Settings
#adapter_settings = BotFrameworkAdapterSettings(app_id=BOT_APP_ID, app_password=BOT_APP_SECRET)
#adapter = BotFrameworkAdapter(adapter_settings)

# 🔹 Inicializamos credenciales y adapter
creds = TenantAwareAppCredentials(BOT_APP_ID, BOT_APP_SECRET, TENANT_ID)
adapter_settings = BotFrameworkAdapterSettings(
    app_id=creds.app_id,
    app_password=creds.password
)
adapter = BotFrameworkAdapter(adapter_settings)

logging.info(
    f"🤖 Bot inicializado con AppId={BOT_APP_ID}, Tenant={TENANT_ID}"
)

# 🔹 Prompts
PROMPT_BASE = "Eres un asistente técnico experto en documentación interna de Confluence."
INTENT_PROMPTS = {
    "resumen": "Resume la información proporcionada de manera clara, concisa y útil.",
    "extraccion": "Extrae datos clave y listados relevantes de la siguiente información.",
    "consulta_directa": "Responde de forma precisa usando solo la información proporcionada.",
    "procedimiento": "Explica paso a paso el procedimiento o proceso mencionado. Estructura tu respuesta de forma secuencial y práctica, numerando los pasos cuando sea posible."
}

def require_basic_auth(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Basic "):
            return Response("Unauthorized", status=401, headers={"WWW-Authenticate": 'Basic realm="Login Required"'})
        try:
            encoded_credentials = auth.split(" ")[1]
            decoded = base64.b64decode(encoded_credentials).decode("utf-8")
            user, pwd = decoded.split(":", 1)
        except Exception:
            return Response("Unauthorized", status=401)
        if user != USERNAME or pwd != PASSWORD:
            return Response("Unauthorized", status=401)
        return await func(*args, **kwargs)
    return wrapper

def log_bot_token():
    try:
        creds = TenantAwareAppCredentials(
            os.getenv("BOT_APP_ID"),
            os.getenv("BOT_APP_SECRET"),
            os.getenv("BOT_TENANT_ID")
        )

        # Obtener el token del tenant corporativo
        token = creds.get_access_token()

        # Decodificar el JWT sin verificar firma
        decoded = jwt.decode(token, options={"verify_signature": False})

        logging.info("🪪 ---- TOKEN DEBUG ----")
        logging.info(f"aud: {decoded.get('aud')}")
        logging.info(f"iss: {decoded.get('iss')}")
        logging.info(f"tid: {decoded.get('tid')}")
        logging.info(f"exp: {decoded.get('exp')}")
        logging.info(f"endpoint usado: {creds.oauth_endpoint}")
        logging.info("-----------------------")

    except Exception as e:
        logging.error(f"Error al obtener token del bot: {e}")


async def on_message_activity(turn_context: TurnContext):
    user_query = turn_context.activity.text.strip()
    logging.info(f"🔍 Usuario pregunta: {user_query}")

    intent = detect_intent(user_query)
    logging.info(f"🔍 Intención detectada: {intent}")

    search_results = search_azure(user_query)
    response_text = generate_response_by_intent(user_query, search_results, intent)

    log_bot_token()   
    #logging.info(f"🤖 Respuesta del bot: {response_text}")
    await turn_context.send_activity(Activity(type=ActivityTypes.message, text=response_text))

def generate_embedding(text: str) -> List[float]:
    """Genera embedding usando Azure OpenAI text-embedding-3-small"""
    
    cleaned_text = text.strip()
    if len(cleaned_text) > 8000:
        cleaned_text = cleaned_text[:8000]
    
    if not cleaned_text:
        return [0.0] * 768
    
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/text-embedding-3-small/embeddings?api-version=2024-02-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY
    }
    
    payload = {
        "input": cleaned_text,
        "model": "text-embedding-3-small",
        "dimensions": 768
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result["data"][0]["embedding"]
        else:
            logging.error(f"Error embedding: {response.status_code}")
            return [0.0] * 768
    except Exception as e:
        logging.error(f"Error generando embedding: {e}")
        return [0.0] * 768

def detect_intent(query):
    return detect_intent_openai(query)

def detect_intent_local(query):
    """Detección de intención local - sin llamadas a API"""
    query_lower = query.lower().strip()
    
    # Palabras clave para PROCEDIMIENTO
    if any(word in query_lower for word in ['cómo', 'como', 'pasos', 'configurar', 'instalar', 'setup', 'crear', 'hacer']):
        return 'procedimiento'
    
    # Palabras clave para RESUMEN
    if any(word in query_lower for word in ['resume', 'resumen', 'qué es', 'que es', 'explica']):
        return 'resumen'
    
    # Palabras clave para EXTRACCIÓN
    if any(word in query_lower for word in ['lista', 'extrae', 'puntos', 'datos']):
        return 'extraccion'
    
    # Por defecto: consulta directa
    return 'consulta_directa'

def detect_intent_openai(query):
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_API_KEY}
    messages = [
        {"role": "system", "content": "Clasifica esta consulta como 'resumen', 'extraccion', 'procedimiento' o 'consulta_directa'. Solo responde con una de esas palabras."},
        {"role": "user", "content": query}
    ]
    payload = {"messages": messages, "temperature": 0, "max_tokens": 10}
    response = requests.post(url, headers=headers, json=payload)
    return response.json().get("choices", [{}])[0].get("message", {}).get("content", "consulta_directa").strip().lower()

def search_azure(query) -> List[Dict]:
    return search_azure_hybrid(query)

def search_azure_hybrid(query: str) -> List[Dict]:
    """
    Búsqueda híbrida: keyword + vector search con RRF automático
    """
    
    logging.info(f"🔍 Búsqueda híbrida para: '{query}'")
    
    # Generar embedding de la query
    query_embedding = generate_embedding(query)
    
    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_SEARCH_API_KEY}
    
    payload = {
        # BÚSQUEDA KEYWORD (tu búsqueda actual)
        "search": query,
        "searchMode": "all",
        
        # BÚSQUEDA VECTORIAL (sintaxis moderna)
        "vectorQueries": [{
            "kind": "vector",
            "vector": query_embedding,
            "fields": "content_vector",
            "k": 50  # Top 50 vectores más similares
        }],
        
        # CONFIGURACIÓN GENERAL
        "top": 15,
        "select": "title,content,url,type",
        "highlight": "content"
        
        # Azure hace RRF (Reciprocal Rank Fusion) automáticamente
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        results = response.json().get("value", [])
        
        # AJUSTE DE UMBRAL PARA BÚSQUEDA HÍBRIDA
        # Los scores híbridos suelen ser más bajos debido al RRF
        min_score_threshold = float(os.getenv("MIN_SCORE_THRESHOLD_HYBRID", "0.01"))  
        filtered_results = [doc for doc in results if doc.get("@search.score", 0) >= min_score_threshold]
        
        logging.info(f"🔍 Búsqueda híbrida '{query}': {len(results)} encontrados, {len(filtered_results)} relevantes")
        return filtered_results
        
    except requests.RequestException as e:
        logging.error(f"❌ Error en búsqueda híbrida: {e}")
        return []
    except Exception as e:
        logging.error(f"❌ Error procesando resultados: {e}")
        return []

def search_azure_classic(query) -> List[Dict]:
    url = f"https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_SEARCH_API_KEY}
    payload = {"search": query, "top": 15, "select": "title,content,url"}
    
    response = requests.post(url, headers=headers, json=payload)
    
    if not response.ok:
        return []

    # 🔹 Filtrar por umbral mínimo de score
    min_score_threshold = float(os.getenv("MIN_SCORE_THRESHOLD", 10))
    results = response.json().get("value", [])
    return [doc for doc in results if doc.get("@search.score", 0) >= min_score_threshold]

def build_context(search_results, max_total_chars=60000):
    context_parts = []
    total_len = 0

    for doc in search_results:
        title = doc.get("title", "Documento sin título")
        content = doc.get("content", "")

        # Tus chunks ya son de 3000, pero cortamos por seguridad
        snippet = content[:3000]

        # 🔹 Un solo salto de línea en lugar de doble
        entry = f"- **{title}**: {snippet}"
        entry_len = len(entry)

        if total_len + entry_len > max_total_chars:
            break

        context_parts.append(entry)
        total_len += entry_len

    # 🔹 Usamos '\n' en lugar de '\n\n' para ahorrar tokens
    return "\n".join(context_parts)


def generate_openai_response(query, context, intent):
    instruction = (
        f"{PROMPT_BASE} {INTENT_PROMPTS.get(intent, INTENT_PROMPTS['consulta_directa'])} "
        "Responde únicamente usando el contenido proporcionado. "
        "Si no encuentras información relevante en los documentos, indica que no hay suficiente información."
    )
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-01"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_API_KEY}
    messages = [
        {"role": "system", "content": instruction},
        {"role": "assistant", "content": context},
        {"role": "user", "content": f"Pregunta: {query}"}
    ]
    payload = {"messages": messages, "temperature": 0.2, "max_tokens": 1200}
    response = requests.post(url, headers=headers, json=payload)
    return response.json().get("choices", [{}])[0].get("message", {}).get("content", "No encontré información relevante.")

def generate_response_by_intent(query, search_results, intent):
    context = build_context(search_results)
    response = generate_openai_response(query, context, intent)

    # 🔹 Recoger URLs únicas con su score
    seen_urls = set()
    enlaces = []
    for doc in search_results:
        url = doc.get("url", "")
        score = doc.get("@search.score", 0.0)
        if url and url not in seen_urls:
            seen_urls.add(url)
            title = doc.get("title", "Documento sin título")
            enlaces.append(f"🔗 [{title}]({url}) (score: {score:.3f})")

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
    
@app.route("/api/ask", methods=["POST"])
@require_basic_auth
async def ask():
    try:
        data = await request.get_json()
        messages = data.get("messages", [])

        if not messages or not isinstance(messages, list):
            return jsonify({"error": "Missing or invalid 'messages' field"}), 400

        user_message = next((msg["content"] for msg in reversed(messages) if msg.get("role") == "user"), None)

        if not user_message:
            return jsonify({"error": "No user message found in 'messages'"}), 400

        logging.info(f"🤖 Pregunta MCP: {user_message}")

        intent = detect_intent(user_message)
        logging.info(f"🔍 Intención detectada: {intent}")

        search_results = search_azure(user_message)
        response_text = generate_response_by_intent(user_message, search_results, intent)

        return jsonify({
            "id": "chatcmpl-mcp-server",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "confubot-mcp",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }
            ]
        })

    except Exception as e:
        logging.error(f"❌ Error en /api/ask MCP: {e}", exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500



if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
