import httpx
import json
import uuid
import logging
import chromadb
from chromadb.utils import embedding_functions
import string
import time

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize ChromaDB client (local persistent vector database)
client = chromadb.PersistentClient(path="./chroma_db")
emb_fn = embedding_functions.DefaultEmbeddingFunction()

collection = client.get_or_create_collection(
    name="recipes",
    embedding_function=emb_fn
)

API_BASE_URL = "https://www.themealdb.com/api/json/v1/1"

def get_ingredients(meal):
    ingredients = []
    for i in range(1, 21):
        ing = meal.get(f"strIngredient{i}")
        meas = meal.get(f"strMeasure{i}")
        if ing and ing.strip():
            ingredients.append({
                "item": ing.strip(),
                "qty": meas.strip() if meas else "1"
            })
    return ingredients

def process_meal(meal):
    title = meal.get("strMeal")
    if not title:
        return
    
    # Avoid duplicates by checking title
    existing = collection.get(where={"title": title})
    if existing['ids']:
        logger.info(f"Skipping {title} - already exists.")
        return

    category = meal.get("strCategory", "Unknown")
    area = meal.get("strArea", "Unknown")
    tags = meal.get("strTags", "")
    instructions = meal.get("strInstructions", "")
    ingredients = get_ingredients(meal)
    ingredients_str = ", ".join([f"{i['qty']} {i['item']}" for i in ingredients])
    
    # BUILD THE RAG DOCUMENT
    document = f"""
    RECIPE TITLE: {title}
    CATEGORY: {category}
    AREA: {area}
    TAGS: {tags}
    INGREDIENTS: {ingredients_str}
    INSTRUCTIONS: {instructions}
    """
    
    metadata = {
        "title": title,
        "category": category,
        "area": area,
        "tags": tags if tags else "",
        "ingredients": json.dumps(ingredients),
        "instructions": instructions,
        "source": f"themealdb_{meal.get('idMeal')}",
        "image": meal.get("strMealThumb", "")
    }
    
    collection.add(
        documents=[document],
        metadatas=[metadata],
        ids=[str(uuid.uuid4())]
    )
    logger.info(f"Added {title} ({category}, {area})")

async def ingest_all():
    async with httpx.AsyncClient() as client_http:
        for letter in string.ascii_lowercase:
            logger.info(f"Fetching recipes starting with: {letter}")
            try:
                response = await client_http.get(f"{API_BASE_URL}/search.php?f={letter}")
                data = response.json()
                meals = data.get("meals")
                if meals:
                    for meal in meals:
                        process_meal(meal)
                else:
                    logger.info(f"No meals found for letter {letter}")
                
                # Small delay to be polite to the API
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error fetching letter {letter}: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(ingest_all())
    logger.info("Ingestion complete!")
