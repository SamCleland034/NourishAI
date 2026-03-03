import os
import uuid
import json
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from recipe_scrapers import scrape_me

import chromadb
from chromadb.utils import embedding_functions

# Initialize ChromaDB client (local persistent vector database)
# This will create a folder named 'chroma_db' in your project directory
client = chromadb.PersistentClient(path="./chroma_db")

# We use the default embedding function (all-MiniLM-L6-v2) for a local self-contained RAG
# This model runs locally on your machine and converts recipe text into vector numbers
emb_fn = embedding_functions.DefaultEmbeddingFunction()

collection = client.get_or_create_collection(
    name="recipes",
    embedding_function=emb_fn
)

app = FastAPI(title="NourishAI Backend - RAG System")

# Enable CORS so the React frontend can talk to this Python backend
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

class PlanRequest(BaseModel):
    plan: Dict[str, Dict[str, Any]]

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

@app.post("/api/scrape")
def scrape_recipe(req: ScrapeRequest):
    """
    RAG Logic Part 1: DATA INGESTION
    1. Scrapes a recipe from a URL using 'recipe-scrapers'
    2. Cleans the data into a text document
    3. Generates embeddings and stores them in ChromaDB
    """
    try:
        scraper = scrape_me(req.url, wild_mode=True)
        
        # Extract data from the website
        title = scraper.title()
        time = scraper.total_time() or 30
        ingredients = scraper.ingredients()
        instructions = scraper.instructions()
        
        # Prepare document for RAG (this text will be converted to a vector)
        document = f"""Recipe: {title}
Time: {time} minutes
Ingredients: {', '.join(ingredients)}
Instructions: {instructions}"""
        
        metadata = {
            "title": title,
            "time": time,
            "ingredients": json.dumps(ingredients),
            "instructions": instructions,
            "source": req.url
        }
        
        recipe_id = str(uuid.uuid4())
        
        # Add to the Vector Database
        collection.add(
            documents=[document],
            metadatas=[metadata],
            ids=[recipe_id]
        )
        return {"status": "success", "id": recipe_id, "title": title}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to scrape recipe: {str(e)}")


@app.post("/api/recommend")
def recommend_meals(req: RecommendRequest):
    """
    RAG Logic Part 2: RETRIEVAL
    1. Takes user preferences (e.g. 'vegan', 'Asian')
    2. Searches the Vector DB for the most similar recipes
    3. Returns them to the frontend to build the meal plan
    """
    prefs = req.preferences
    
    # Construct a search query based on preferences
    query_parts = []
    if prefs.dietary:
        query_parts.append(" ".join(prefs.dietary))
    if prefs.cuisines:
        query_parts.append(" ".join(prefs.cuisines))
    
    query = req.query or " ".join(query_parts)
    if not query.strip():
        query = "healthy delicious meals"
        
    # Query ChromaDB (Vector Search)
    results = collection.query(
        query_texts=[query],
        n_results=15
    )
    
    recipes = []
    if results['metadatas'] and results['metadatas'][0]:
        for i, meta in enumerate(results['metadatas'][0]):
            time = meta.get("time", 30)
            
            # Post-retrieval filtering (ensure it fits the user's max time)
            if time > prefs.maxTime:
                continue
                
            raw_ingredients = json.loads(meta.get("ingredients", "[]"))
            parsed_ings = []
            
            # Formatting for frontend display
            for ing in raw_ingredients:
                parsed_ings.append({"item": ing, "qty": "1", "unit": "unit"})
                
            recipes.append({
                "id": results['ids'][0][i],
                "name": meta.get("title", "Unknown"),
                "cuisine": "Scraped", 
                "tags": prefs.dietary,
                "time": time,
                "calories": 400, 
                "ingredients": parsed_ings,
                "instructions": meta.get("instructions", "")
            })
            
    return {"recipes": recipes}

@app.post("/api/grocery-list")
def generate_grocery_list(req: PlanRequest):
    """
    Delivery Logic:
    1. Aggregates all ingredients from the 7-day plan
    2. Generates direct search links for Instacart and Amazon Fresh
    """
    ingredient_map = {}
    
    for day, meals in req.plan.items():
        for meal_type, recipe in meals.items():
            if not recipe: continue
            for ing in recipe.get("ingredients", []):
                key = ing["item"].lower()
                # Basic parsing to combine items (e.g. 1 egg + 2 eggs = 3 eggs)
                try:
                    qty = float(ing.get("qty", 1) or 1)
                except:
                    qty = 1.0
                
                if key not in ingredient_map:
                    ingredient_map[key] = {
                        "item": ing["item"], 
                        "qty": qty, 
                        "unit": ing.get("unit", "")
                    }
                else:
                    ingredient_map[key]["qty"] += qty
                    
    grocery_list = list(ingredient_map.values())
    
    # Generate auto-delivery shopping links
    for item in grocery_list:
        search_term = item['item'].replace(' ', '+')
        # Link to Instacart Search
        item["instacart_url"] = f"https://www.instacart.com/store/s?k={search_term}"
        # Link to Amazon Fresh Search
        item["amazon_url"] = f"https://www.amazon.com/s?k={search_term}&i=amazonfresh"
        item["checked"] = False
        
    return {"grocery_list": grocery_list}

if __name__ == "__main__":
    import uvicorn
    # Start the server on localhost:8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
