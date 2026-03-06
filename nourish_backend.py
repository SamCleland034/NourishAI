import os
import uuid
import json
import logging
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from recipe_scrapers import scrape_me

import chromadb
from chromadb.utils import embedding_functions

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize ChromaDB client (local persistent vector database)
client = chromadb.PersistentClient(path="./chroma_db")

# We use the default embedding function (all-MiniLM-L6-v2) for local RAG
# This model converts recipe text into 384-dimensional vector numbers
emb_fn = embedding_functions.DefaultEmbeddingFunction()

collection = client.get_or_create_collection(
    name="recipes",
    embedding_function=emb_fn
)

# POPULAR RECIPE SOURCES FOR INITIAL DATABASE POPULATION
# We pull from real URLs instead of hardcoded data
SEED_URLS = [
    "https://www.allrecipes.com/recipe/23600/world-best-lasagna/",
    "https://www.allrecipes.com/recipe/223042/chicken-parmesan-casserole/",
    "https://www.allrecipes.com/recipe/242352/greek-lemon-chicken-and-potatoes/",
    "https://www.allrecipes.com/recipe/222002/classic-macaroni-and-cheese/",
    "https://www.allrecipes.com/recipe/24035/kalbi-korean-bbq-short-ribs/",
    "https://www.allrecipes.com/recipe/21014/good-old-fashioned-pancakes/",
    "https://www.allrecipes.com/recipe/15800/best-chocolate-chip-cookies/",
    "https://www.allrecipes.com/recipe/228293/curry-stand-chicken-tikka-masala/",
    "https://www.allrecipes.com/recipe/70163/easy-meatloaf/",
    "https://www.allrecipes.com/recipe/143809/best-steak-marinade-in-existence/",
    "https://www.foodnetwork.com/recipes/alton-brown/the-chewy-recipe-1909072",
    "https://www.foodnetwork.com/recipes/ina-garten/perfect-roast-chicken-recipe-1940592",
    "https://www.foodnetwork.com/recipes/bobby-flay/perfectly-grilled-steak-recipe-1950346",
    "https://www.allrecipes.com/recipe/11679/homemade-mac-and-cheese/",
    "https://www.allrecipes.com/recipe/25473/the-perfect-margarita/",
    "https://www.allrecipes.com/recipe/21176/apple-pie-by-grandma-ople/",
    "https://www.allrecipes.com/recipe/16330/stuffed-peppers/",
    "https://www.allrecipes.com/recipe/16348/old-fashioned-beef-stew/",
    "https://www.allrecipes.com/recipe/20144/banana-banana-bread/",
    "https://www.allrecipes.com/recipe/236609/honey-garlic-chicken-thighs/"
]

app = FastAPI(title="NourishAI Backend - RAG System")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str

class Preference(BaseModel):
    dietary: List[str] = []
    cuisines: List[str] = []
    maxTime: int = 60

class RecommendRequest(BaseModel):
    preferences: Preference
    query: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = []

class PlanRequest(BaseModel):
    plan: Dict[str, Dict[str, Any]]

def process_and_store_recipe(url: str):
    """Scrapes a URL and stores it in ChromaDB with proper RAG structure."""
    try:
        scraper = scrape_me(url, wild_mode=True)
        title = scraper.title()
        
        # Avoid duplicates
        existing = collection.get(where={"title": title})
        if existing['ids']:
            return {"status": "skipped", "reason": "Already exists", "title": title}
            
        ingredients = scraper.ingredients()
        instructions = scraper.instructions()
        time = scraper.total_time() or 30
        
        # BUILD THE RAG DOCUMENT
        # We structure this so the embedding model captures the essence of the meal
        document = f"""
        RECIPE TITLE: {title}
        COOK TIME: {time} minutes
        INGREDIENTS: {', '.join(ingredients)}
        INSTRUCTIONS: {instructions}
        """
        
        metadata = {
            "title": title,
            "time": time,
            "ingredients": json.dumps(ingredients),
            "instructions": instructions,
            "source": url
        }
        
        collection.add(
            documents=[document],
            metadatas=[metadata],
            ids=[str(uuid.uuid4())]
        )
        return {"status": "success", "title": title}
    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return {"status": "error", "url": url, "error": str(e)}

@app.on_event("startup")
async def startup_event():
    """On launch, check if DB is empty and populate from real web sources."""
    count = collection.count()
    if count == 0:
        logger.info("🌱 Database empty. Scraping popular recipe sources for initial RAG database...")
        for url in SEED_URLS[:10]: # Scrape first 10 immediately
            process_and_store_recipe(url)
        logger.info(f"✅ Initial RAG database seeded with {collection.count()} recipes.")

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>NourishAI Backend</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
                       background-color: #080d08; color: #e0d8c8; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .card { background: #0f180f; border: 1px solid #1c301c; padding: 40px; border-radius: 14px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
                h1 { color: #6ec86e; margin-bottom: 10px; }
                p { color: #4a7a4a; margin-bottom: 25px; }
                .btn { display: inline-block; background: #2a6a2a; color: #c0e0c0; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; transition: background 0.2s; }
                .btn:hover { background: #3a7a3a; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🌿 NourishAI Backend</h1>
                <p>The RAG-powered recipe engine is running.</p>
                <a href="/docs" class="btn">View API Documentation</a>
            </div>
        </body>
    </html>
    """

@app.get("/api/recipes")
def get_all_recipes():
    results = collection.get()
    recipes = []
    for i, meta in enumerate(results['metadatas']):
        raw_ingredients = json.loads(meta.get("ingredients", "[]"))
        ingredients = []
        for ing in raw_ingredients:
            if isinstance(ing, dict):
                ingredients.append(ing)
            else:
                ingredients.append({"item": ing, "qty": "1", "unit": "unit"})

        recipes.append({
            "id": results['ids'][i],
            "name": meta.get("title", "Unknown"),
            "time": meta.get("time", 30),
            "ingredients": ingredients,
            "instructions": meta.get("instructions", ""),
            "cuisine": meta.get("area", meta.get("cuisine", "Scraped")),
            "category": meta.get("category", "General"),
            "image": meta.get("image", "")
        })
    return {"recipes": recipes}

@app.post("/api/seed")
def seed_database(background_tasks: BackgroundTasks):
    """Seeds the database with high-quality recipes from the web."""
    # Run the remaining seed URLs in the background to not block the request
    for url in SEED_URLS[10:]:
        background_tasks.add_task(process_and_store_recipe, url)
    return {"status": "success", "message": "Background seeding started for 10+ more recipes."}

@app.post("/api/scrape")
def scrape_recipe(req: ScrapeRequest):
    result = process_and_store_recipe(req.url)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.post("/api/recommend")
def recommend_meals(req: RecommendRequest):
    prefs = req.preferences
    query_parts = []
    if prefs.dietary: query_parts.append(" ".join(prefs.dietary))
    if prefs.cuisines: query_parts.append(" ".join(prefs.cuisines))
    
    query = req.query or " ".join(query_parts)
    if not query.strip(): query = "healthy delicious meals"
        
    results = collection.query(query_texts=[query], n_results=10)
    
    recipes = []
    if results['metadatas'] and results['metadatas'][0]:
        for i, meta in enumerate(results['metadatas'][0]):
            if meta.get("time", 30) > prefs.maxTime: continue
            
            raw_ingredients = json.loads(meta.get("ingredients", "[]"))
            formatted_ingredients = []
            for ing in raw_ingredients:
                if isinstance(ing, dict):
                    formatted_ingredients.append({
                        "item": ing.get("item", "Unknown"),
                        "qty": ing.get("qty", "1"),
                        "unit": ing.get("unit", "")
                    })
                else:
                    formatted_ingredients.append({"item": ing, "qty": "1", "unit": "unit"})

            recipes.append({
                "id": results['ids'][0][i],
                "name": meta.get("title", "Unknown"),
                "cuisine": meta.get("area", meta.get("cuisine", "RAG Retrieval")), 
                "time": meta.get("time", 30),
                "ingredients": formatted_ingredients,
                "instructions": meta.get("instructions", ""),
                "category": meta.get("category", "General"),
                "image": meta.get("image", "")
            })
    return {"recipes": recipes}

import litellm

# ... (existing imports)

@app.post("/api/chat")
def chat_with_rag(req: ChatRequest):
    """
    FULL RAG PIPELINE:
    1. Query ChromaDB for top 3 matching recipes.
    2. Format recipes into a structured context.
    3. Use LiteLLM to generate a personalized recommendation.
    4. Return both the AI text and the recipe objects for the UI.
    """
    logger.info(f"Received chat request: {req.message}")
    
    # 1. Retrieval
    try:
        results = collection.query(
            query_texts=[req.message],
            n_results=3
        )
        logger.info(f"Retrieved {len(results['ids'][0]) if results['ids'] else 0} recipes from ChromaDB")
    except Exception as e:
        logger.error(f"ChromaDB Query Error: {e}")
        results = {'metadatas': [[]], 'ids': [[]]}
    
    # 2. Context Construction
    recipes_context = ""
    recipe_objects = []
    
    if results['metadatas'] and results['metadatas'][0]:
        for i, meta in enumerate(results['metadatas'][0]):
            title = meta.get("title", "Unknown")
            area = meta.get("area", "Unknown")
            cat = meta.get("category", "General")
            inst = meta.get("instructions", "")[:300] # Snippet for prompt
            
            logger.info(f"Matched recipe: {title}")
            recipes_context += f"\n- {title} ({area} {cat}): {inst}...\n"
            
            # Prepare clean objects for the frontend
            try:
                raw_ings = meta.get("ingredients", "[]")
                ingredients = json.loads(raw_ings) if isinstance(raw_ings, str) else raw_ings
            except:
                ingredients = []

            recipe_objects.append({
                "id": results['ids'][0][i],
                "name": title,
                "cuisine": area,
                "category": cat,
                "image": meta.get("image", ""),
                "ingredients": ingredients,
                "instructions": meta.get("instructions", "")
            })

    # 3. LLM Generation
    system_prompt = f"""
    You are NourishAI, a helpful culinary assistant. 
    Use the following recipes from our database to answer the user's request.
    If the recipes aren't relevant, still be helpful but mention what we have available.
    
    AVAILABLE RECIPES:
    {recipes_context if recipes_context else "No specific recipes found in database."}
    
    Keep your response friendly, concise, and appetizing.
    """

    # Convert history to LiteLLM format if it's not already
    formatted_history = []
    for h in req.history:
        formatted_history.append({"role": h.get("role"), "content": h.get("content")})

    try:
        logger.info("Calling LiteLLM...")
        response = litellm.completion(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                *formatted_history,
                {"role": "user", "content": req.message}
            ]
        )
        ai_message = response.choices[0].message.content
        logger.info("LiteLLM response received successfully")
    except Exception as e:
        logger.error(f"LiteLLM Error: {e}")
        ai_message = "I found some recipes for you! Check them out below."

    return {
        "message": ai_message,
        "recipes": recipe_objects
    }

@app.post("/api/grocery-list")
def generate_grocery_list(req: PlanRequest):
    ingredient_map = {}
    for day, meals in req.plan.items():
        for meal_type, recipe in meals.items():
            if not recipe: continue
            for ing in recipe.get("ingredients", []):
                key = ing["item"].lower()
                try:
                    qty = float(ing.get("qty", 1) or 1)
                except:
                    qty = 1.0
                if key not in ingredient_map:
                    ingredient_map[key] = {"item": ing["item"], "qty": qty, "unit": ing.get("unit", "")}
                else:
                    ingredient_map[key]["qty"] += qty
                    
    grocery_list = list(ingredient_map.values())
    for item in grocery_list:
        search_term = item['item'].replace(' ', '+')
        item["instacart_url"] = f"https://www.instacart.com/store/s?k={search_term}"
        item["amazon_url"] = f"https://www.amazon.com/s?k={search_term}&i=amazonfresh"
        item["checked"] = False
        
    return {"grocery_list": grocery_list}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
