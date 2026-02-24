# ELECTRIA API

Backend API para ELECTRIA - Inteligencia Artificial para el Mercado Eléctrico.

## Stack Tecnológico

- **Framework**: FastAPI (Python 3.12)
- **Base de Datos**: PostgreSQL (Supabase) + TimescaleDB
- **Vector DB**: Pinecone
- **LLM**: Claude API (Anthropic)
- **Task Queue**: Celery + Redis
- **Storage**: Cloudflare R2

## Estructura del Proyecto

```
electria-api/
├── app/
│   ├── api/v1/           # Endpoints REST
│   │   ├── auth/         # Autenticación
│   │   ├── chat/         # Chat RAG con Claude
│   │   ├── search/       # Búsqueda de documentos
│   │   ├── dashboard/    # Datos del mercado
│   │   ├── alerts/       # Sistema de alertas
│   │   └── users/        # Gestión de usuarios
│   ├── core/             # Configuración
│   ├── services/         # Lógica de negocio
│   ├── models/           # Modelos SQLAlchemy
│   ├── schemas/          # Schemas Pydantic
│   └── workers/          # Tareas Celery
├── packages/
│   ├── rag/              # Pipeline RAG
│   ├── scrapers/         # Scrapers de datos
│   └── countries/        # Config por país
├── tests/
├── scripts/
└── docs/
```

## Setup Local

### Requisitos

- Python 3.12+
- Redis (para Celery)
- Cuentas en: Supabase, Pinecone, Anthropic, OpenAI

### Instalación

```bash
# Clonar repositorio
git clone https://github.com/[tu-usuario]/electria-api.git
cd electria-api

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -e ".[dev]"

# Copiar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar servidor de desarrollo
uvicorn app.main:app --reload
```

### Variables de Entorno

Ver `.env.example` para la lista completa. Las mínimas requeridas son:

```bash
SECRET_KEY=tu-clave-secreta-de-32-caracteres
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_ANON_KEY=tu-anon-key
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
```

## Desarrollo

```bash
# Ejecutar tests
pytest

# Linting
ruff check .
ruff format .

# Type checking
mypy app
```

## API Endpoints

Una vez corriendo, visita:
- Documentación: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Endpoints Principales

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/chat` | Chat con RAG |
| GET | `/api/v1/search` | Buscar documentos |
| GET | `/api/v1/dashboard/summary` | Resumen del mercado |
| GET | `/api/v1/dashboard/cmg` | Costos marginales |
| POST | `/api/v1/alerts` | Crear alerta |

## Arquitectura

```
Usuario → API Gateway → [Auth] → Service Layer → Data Layer
                                      │
                        ┌─────────────┼─────────────┐
                        │             │             │
                    Claude API    Pinecone     PostgreSQL
                    (Respuestas)  (Vectores)   (Datos/Users)
```

## Licencia

Propietario - ELECTRIA
