# Confubot Teams

Chatbot de Microsoft Teams que responde preguntas utilizando Azure Cognitive Search (búsqueda híbrida keyword + vector) y Azure OpenAI. Sirve como asistente técnico para documentación interna de Confluence.

## Arquitectura

```
Teams → Bot Framework → Quart Server → Azure Cognitive Search → Azure OpenAI
                              ↓
                        /api/ask (MCP)
```

- **Servidor**: Quart async (single-file `app.py`)
- **Búsqueda**: Azure Cognitive Search con búsqueda híbrida (BM25 + vector similarity)
- **LLM**: Azure OpenAI (GPT-4o-mini)
- **Embeddings**: text-embedding-3-large (1536 dimensiones)
- **Integración**: Bot Framework para Microsoft Teams

### Flujo de una consulta

1. Usuario envía pregunta
2. `detect_intent()` clasifica la intención (resumen/extraccion/procedimiento/consulta_directa)
3. `search_azure_hybrid()` busca en Azure Cognitive Search
4. `build_context()` construye el contexto con los resultados (máx 60k chars)
5. `generate_openai_response()` genera respuesta con Azure OpenAI
6. Se devuelve respuesta con enlaces a fuentes y scores de relevancia

## Endpoints

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `/api/messages` | POST | Bot Framework | Recibe actividades de Microsoft Teams |
| `/api/ask` | POST | Basic Auth | API REST para clientes MCP |

### Ejemplo `/api/ask`

```bash
curl -X POST https://your-app.azurewebsites.net/api/ask \
  -u "usuario:password" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "¿Cómo configuro X?"}]}'
```

## Requisitos

- Python 3.11+
- Dependencias: ver `requirements.txt`

## Variables de entorno

### Requeridas

| Variable | Descripción |
|----------|-------------|
| `BOT_APP_ID` | ID de la aplicación Azure Bot |
| `BOT_APP_SECRET` | Secret de la aplicación Azure Bot |
| `BOT_TENANT_ID` | Tenant ID de Azure AD |
| `AZURE_SEARCH_SERVICE` | Nombre del servicio Azure Cognitive Search |
| `AZURE_SEARCH_API_KEY` | API Key de Azure Cognitive Search |
| `AZURE_SEARCH_INDEX` | Nombre del índice de búsqueda |
| `AZURE_OPENAI_ENDPOINT` | Endpoint de Azure OpenAI |
| `AZURE_OPENAI_API_KEY` | API Key de Azure OpenAI |
| `AZURE_OPENAI_DEPLOYMENT` | Nombre del deployment de Azure OpenAI |

### Opcionales

| Variable | Default | Descripción |
|----------|---------|-------------|
| `BASIC_AUTH_USER` | - | Usuario para `/api/ask` |
| `BASIC_AUTH_PASS` | - | Password para `/api/ask` |
| `PORT` | 8000 | Puerto del servidor |
| `MIN_SCORE_THRESHOLD_HYBRID` | 0.01 | Score mínimo para búsqueda híbrida |
| `MIN_SCORE_THRESHOLD` | 10 | Score mínimo para búsqueda keyword |

## Desarrollo local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar servidor
python app.py

# O con hypercorn directamente
hypercorn app:app --bind 0.0.0.0:8000
```

### Pruebas con Bot Framework Emulator

Para probar el bot localmente con el [Bot Framework Emulator](https://github.com/Microsoft/BotFramework-Emulator), las credenciales del bot deben estar vacías:

```env
BOT_APP_ID=
BOT_APP_SECRET=
BOT_TENANT_ID=
```

1. Ejecutar el servidor: `python app.py`
2. Abrir Bot Framework Emulator
3. Conectar a `http://localhost:8000/api/messages`
4. Dejar campos App ID y Password vacíos

## Despliegue en Azure

| Branch | App Service | Entorno |
|--------|-------------|---------|
| `main` | `confubot-teams-pro` | Producción |
| `develop` | `confubot-teams` | Desarrollo |

### CI/CD

- GitHub Actions con autenticación OIDC hacia Azure
- Push a `main` o `develop` dispara despliegue automático
- Azure App Service ejecuta con hypercorn (startup command configurado)
