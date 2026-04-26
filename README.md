# NourishAI 🌿

NourishAI is an intelligent, RAG-powered (Retrieval-Augmented Generation) meal planning and healthy eating companion. It combines a rich database of global recipes with advanced AI to help you plan your week, discover new tastes, and stay on track with your nutritional goals.

## 🚀 Key Features

### 1. Smart Chat & Recipe Discovery
*   **AI Chef Assistant:** Ask for recipes based on ingredients, mood, or dietary needs.
*   **Initial Greeting:** Get welcomed by a helpful assistant ready to guide your meal planning.
*   **Visual Discovery:** Every recipe returned includes high-quality imagery and detailed step-by-step instructions.

### 2. Intelligent Weekly Planner
*   **AI Planner Prompt:** Don't just pick recipes—ask the AI to "Arrange a high-protein week" or "Plan a vegan Monday and Tuesday." The AI will automatically structure your grid.
*   **🪄 Magic Auto-Fill:** Instantly populate your entire week with a single click. The system analyzes your favorites and preferences to pick 21 diverse, relevant meals (including smart Breakfast detection).
*   **🔁 Recurring Schedules:** Save your perfect week as a "Recurring Template." Any future week you visit that is empty will automatically pull from this template, automating your long-term planning.
*   **Drag-and-Drop Feel:** Click any empty cell to add recipes from your favorites or recommendations.

### 3. Google Calendar Integration
*   **One-Click Export:** Seamlessly sync your weekly plan to your Google Calendar.
*   **Detailed Events:** Each calendar event includes the recipe name and a full list of required ingredients in the description.

### 4. Robust Image System
*   **Automated Repair:** A background system ensures that images from TheMealDB and synthetic AI-generated recipes are always valid.
*   **Smart Fallbacks:** If a source image is ever broken, the app automatically generates a clean, readable placeholder so you never see a "black box."

## 🛠️ Technical Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 + Vite, Vanilla CSS (dark-mode) |
| **Backend** | FastAPI (Python), served as Vercel Serverless Functions |
| **Vector Store** | Pinecone (RAG recipe search) |
| **Relational DB** | SQLite (local dev) or Supabase Postgres (production) |
| **AI / LLM** | LiteLLM → Gemini 2.0 Flash (chat, planner, grocery) |
| **Embeddings** | OpenAI `text-embedding-3-small` (1536 dims) |
| **Auth** | SHA-256 hashed passwords; Google OAuth 2.0 for Calendar |

## ⚙️ Environment Variables

Copy `.env.cloud.example` to `.env` and fill in the values you need.

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

## 🏃 Local Development

### 1. Install dependencies

```bash
# Python backend
pip install -r api/requirements.txt

# React frontend
npm install
```

### 2. Configure environment

```bash
cp .env.cloud.example .env
# Edit .env — at minimum set GEMINI_API_KEY, OPENAI_API_KEY, PINECONE_API_KEY
```

If `SUPABASE_URL` and `SUPABASE_KEY` are absent, the backend automatically uses **SQLite** (`nourish.db` in the project root). No database setup is required.

To force a specific mode:
```bash
DB_MODE=sqlite    # always use local SQLite
DB_MODE=supabase  # always use Supabase (requires keys)
```

### 3. Start the backend

```bash
python -m uvicorn api.index:app --reload --port 8000
```

### 4. Start the frontend

```bash
npm run dev
```

The app will be available at `http://localhost:5173`. The frontend proxies `/api/*` requests to the backend via Vite's dev server config.

### 5. Populate the recipe database (first time only)

```bash
# Ingest TheMealDB recipes into Pinecone
python ingest_themealdb.py

# (Optional) Generate and add synthetic recipes
python generate_synthetic_recipes.py

# (Optional) Backfill nutrition data for existing recipes
python backfill_nutrition.py
```

## 🚢 Deploying to Vercel

1. Push to GitHub.
2. Import the repo in [Vercel](https://vercel.com) — it auto-detects the Vite framework.
3. Set all environment variables in **Vercel → Project → Settings → Environment Variables** (see table above). Include both `SUPABASE_URL` and `SUPABASE_KEY` — their presence automatically switches the backend to Supabase mode.
4. Deploy. The `vercel.json` routing config forwards `/api/*` to `api/index.py` and everything else to the React SPA.

### Supabase table setup

Run the following SQL once in your Supabase project's **SQL Editor**:

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

## 🐳 Docker (optional)

```bash
docker compose up --build
```

This starts both the FastAPI backend and the Vite frontend in containers. See `Dockerfile.backend`, `Dockerfile.frontend`, and `docker-compose.yml` for configuration.

---
*Built for healthy living, powered by AI.*
