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

*   **Frontend:** React (Vite), Tailwind-inspired Vanilla CSS for a premium dark-mode aesthetic.
*   **Backend:** FastAPI (Python).
*   **Database:** SQLite (Users/Schedules/Favorites) + ChromaDB (Vector store for RAG).
*   **AI/LLM:** LiteLLM (supporting GPT-4o-mini and others) for chat and arrangement logic.
*   **Data Ingestion:** Custom scripts for TheMealDB API and synthetic recipe generation.

## 🏃 Getting Started

1.  **Backend:**
    ```bash
    uvicorn nourish_backend:app --reload
    ```
2.  **Frontend:**
    ```bash
    npm run dev
    ```
3.  **Database Setup (Optional):**
    Run `python ingest_themealdb.py` to populate your local vector store.

---
*Built for healthy living, powered by AI.*
