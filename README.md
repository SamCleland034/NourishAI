# 🌿 NourishAI - RAG-Powered Recipe Intelligence

NourishAI is an intelligent culinary assistant that uses **Retrieval-Augmented Generation (RAG)** to provide personalized recipe recommendations. It combines a local vector database (ChromaDB) with large language models (via LiteLLM) to "know" about hundreds of real-world recipes and answer your cooking questions.

---

## 🏗️ Architecture & Tech Stack

- **Frontend:** React (Vite) with a custom CSS culinary theme.
- **Backend:** FastAPI (Python) serving as the orchestration layer.
- **Vector Database:** ChromaDB (Local Persistent) for high-speed similarity search.
- **Embeddings:** `all-MiniLM-L6-v2` (ONNX) running locally to convert recipes into 384-dimensional vectors.
- **LLM Integration:** LiteLLM (supports OpenAI, Anthropic, Gemini, etc.) for conversational RAG.
- **Data Source:** TheMealDB API + Synthetic AI-generated recipes.

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.12+** (Recommended: [uv](https://github.com/astral-sh/uv))
- **Node.js & npm**
- **API Key:** Set your `OPENAI_API_KEY` (or other provider keys) in your environment.

### 2. Installation
```powershell
# Install Python dependencies
uv sync

# Install Frontend dependencies
npm install
```

### 3. Data Ingestion (Seeding the Brain)
You need to fill the database before the AI can "know" anything.

- **Ingest 600+ real recipes from TheMealDB:**
  ```powershell
  uv run ingest_themealdb.py
  ```
- **Generate custom AI recipes (Synthetic Data):**
  ```powershell
  uv run generate_synthetic_recipes.py --count 5 --model gpt-4o-mini
  ```

---

## 🛠️ Tools & Usage

### Running the System
1. **Start the Backend:**
   ```powershell
   uv run nourish_backend.py
   ```
2. **Start the Frontend:**
   ```powershell
   npm run dev
   ```

### Inspecting the Database
Use the CLI tool to see what's inside your ChromaDB:
```powershell
# See stats (Category/Cuisine distribution)
uv run inspect_db.py --stats

# Search for a specific recipe with full details
uv run inspect_db.py --search "Kebab" --full

# List the last 10 added recipes
uv run inspect_db.py --list 10
```

---

## 🧠 How the RAG Pipeline Works

1. **User Query:** You ask, *"I want a spicy chicken dish from Turkey."*
2. **Retrieval:** The backend converts your question into a vector and searches **ChromaDB** for the top 3 most similar recipes (e.g., *Adana Kebab*).
3. **Augmentation:** The system builds a prompt: *"You are NourishAI. Use these recipes [Adana Kebab, etc.] to answer the user: 'I want a spicy chicken dish from Turkey'."*
4. **Generation:** The **LLM** (GPT-4o/Claude) reads the retrieved recipes and writes a friendly response.
5. **Visualization:** The backend returns the text **plus** the raw metadata, allowing the React UI to render rich cards and images alongside the chat.

---

## 📂 Project Structure

- `nourish_backend.py`: The FastAPI server & RAG logic.
- `ingest_themealdb.py`: Web scraper & ingestion script.
- `generate_synthetic_recipes.py`: AI-powered recipe generator using LiteLLM.
- `inspect_db.py`: CLI debugging tool for the vector DB.
- `src/App.jsx`: The interactive React chat & recipe viewer.
- `chroma_db/`: Directory where your vector data is stored.
