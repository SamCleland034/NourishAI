# NourishAI

NourishAI is a RAG-powered (Retrieval-Augmented Generation) meal planning and healthy eating companion. It combines a rich database of global recipes with advanced AI to help you plan your week, discover new tastes, and stay on track with your nutritional goals.

## Project Structure

```
NourishAI/
├── api/                    # FastAPI backend (Vercel serverless)
│   ├── index.py            # All API routes and business logic
│   └── requirements.txt    # Python deps for Vercel
├── src/                    # React frontend
│   ├── App.jsx             # Main application component
│   └── main.jsx            # Vite entry point
├── scripts/                # Data pipeline & utility scripts
│   ├── ingest_themealdb.py
│   ├── ingest_spoonacular.py
│   ├── ingest_recipenlg.py
│   ├── ingest_traderjoes.py
│   ├── generate_synthetic_recipes.py
│   ├── backfill_nutrition.py
│   ├── migrate_to_pinecone.py
│   ├── repair_db_images.py
│   └── inspect_db.py
├── tests/                  # API and endpoint tests
│   ├── test_planner_api.py
│   └── test_search_endpoint.py
├── evaluations/            # RAG evaluation notebook + outputs
│   ├── rag_evaluation.ipynb
│   └── outputs/
├── docs/                   # Project documentation
│   └── report.tex          # Full project report (LaTeX)
├── static/                 # Locally served recipe images
├── index.html              # Vite HTML entry
├── vite.config.js
├── vercel.json             # Vercel routing config
├── pyproject.toml          # Python project & deps (uv)
└── docker-compose.yml      # Optional Docker setup
```

## Key Features

### Smart Chat & Recipe Discovery
- **AI Chef Assistant:** Ask for recipes based on ingredients, mood, or dietary needs.
- **Visual Discovery:** Every recipe includes high-quality imagery and step-by-step instructions.

### Intelligent Weekly Planner
- **AI Planner Prompt:** Ask the AI to "Arrange a high-protein week" or "Plan a vegan Monday and Tuesday."
- **Magic Auto-Fill:** Instantly populate your entire week with one click, using your favorites and preferences.
- **Recurring Schedules:** Save your perfect week as a recurring template for automatic future planning.
- **Nutritional Stats:** Real-time daily and weekly calorie/macro breakdown that updates as you add recipes.

### Grocery List & Meal Prep Guide
- **Auto-Generated Grocery List:** Aggregates all ingredients from your weekly plan, grouped by category.
- **Meal Prep Guide:** Step-by-step batching instructions for efficient cooking.
- **Export Options:** Copy to clipboard or download as CSV for both the grocery list and prep guide.

### Google Calendar Integration
- **One-Click Export:** Sync your weekly meal plan to Google Calendar with full ingredient details in each event.

## Technical Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 + Vite, Vanilla CSS (dark-mode) |
| **Backend** | FastAPI (Python), served as Vercel Serverless Functions |
| **Vector Store** | Pinecone (RAG recipe search, 697 indexed recipes) |
| **Relational DB** | SQLite (local dev) or Supabase Postgres (production) |
| **AI / LLM** | LiteLLM → Gemini 2.5 Flash (chat, planner, grocery, prep guide) |
| **Embeddings** | OpenAI `text-embedding-3-small` (1536 dims) |
| **Auth** | SHA-256 hashed passwords; Google OAuth 2.0 for Calendar |

## Environment Variables

Copy `.env.cloud.example` to `.env` and fill in the values.

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google AI Studio key for LiteLLM |
| `OPENAI_API_KEY` | Yes | Used for recipe embeddings |
| `PINECONE_API_KEY` | Yes | Pinecone vector store |
| `PINECONE_INDEX_NAME` | No | Defaults to `recipes` |
| `DB_MODE` | No | `sqlite` or `supabase` (auto-detected) |
| `SUPABASE_URL` | Supabase only | Project URL from Supabase dashboard |
| `SUPABASE_KEY` | Supabase only | Anon/public key from Supabase dashboard |
| `REDIRECT_URI` | Google Cal | OAuth callback URL |
| `FRONTEND_URL` | No | Allowed CORS origin (default: `http://localhost:5173`) |

## Local Development

### 1. Install dependencies

```bash
# Python backend (recommended: uv)
uv sync

# React frontend
npm install
```

### 2. Configure environment

```bash
cp .env.cloud.example .env
# Edit .env — at minimum set GEMINI_API_KEY, OPENAI_API_KEY, PINECONE_API_KEY
```

If `SUPABASE_URL` and `SUPABASE_KEY` are absent, the backend automatically uses **SQLite** (`nourish.db`). No database setup required.

### 3. Start the backend

```bash
uv run uvicorn api.index:app --reload --port 8000
```

### 4. Start the frontend

```bash
npm run dev
```

The app will be available at `http://localhost:5173`. The frontend proxies `/api/*` requests to the backend via Vite's dev server config.

### 5. Populate the recipe database (first time only)

```bash
# Ingest TheMealDB recipes into Pinecone
python scripts/ingest_themealdb.py

# (Optional) Generate and add synthetic recipes
python scripts/generate_synthetic_recipes.py

# (Optional) Backfill nutrition data for existing recipes
python scripts/backfill_nutrition.py
```

## Deploying to Vercel

1. Push to GitHub.
2. Import the repo in [Vercel](https://vercel.com) — it auto-detects the Vite framework.
3. Set all environment variables in **Vercel → Project → Settings → Environment Variables** (see table above). Presence of `SUPABASE_URL` + `SUPABASE_KEY` automatically switches the backend to Supabase mode.
4. Deploy. The `vercel.json` routing config forwards `/api/*` to `api/index.py` and everything else to the React SPA.

### Supabase table setup

Run the following SQL once in your Supabase project's SQL Editor:

```sql
create table users (
  id serial primary key,
  username text unique not null,
  password_hash text not null
);

create table favorites (
  id serial primary key,
  user_id integer not null,
  recipe_id text not null,
  recipe_data jsonb not null,
  unique (user_id, recipe_id)
);

create table schedules (
  id serial primary key,
  user_id integer not null,
  week_id text not null,
  schedule_json jsonb not null,
  unique (user_id, week_id)
);

create table google_tokens (
  id serial primary key,
  user_id integer not null unique,
  token_json text not null
);
```

## Docker (optional)

```bash
docker compose up --build
```

Starts both the FastAPI backend and the Vite frontend in containers. See `Dockerfile.backend`, `Dockerfile.frontend`, and `docker-compose.yml` for configuration.

## RAG Evaluation

The `evaluations/` directory contains a Jupyter notebook (`rag_evaluation.ipynb`) that measures retrieval quality across all five RAG-powered endpoints using Precision@K and Recall@K metrics, with Gemini 2.5 Flash as an LLM judge. Results are exported to `evaluations/outputs/`. The full methodology and findings are documented in `docs/report.tex`.

---
*Built for healthy living, powered by AI.*
