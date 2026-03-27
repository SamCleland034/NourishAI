import httpx
import json
import uuid
import logging
import chromadb
from chromadb.utils import embedding_functions
import string
import time
import os
import litellm

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# STATIC CONFIG
DEFAULT_MODEL = "gemini/gemini-2.0-flash"
IMAGES_DIR = os.path.join("static", "recipe_images")
os.makedirs(IMAGES_DIR, exist_ok=True)

# Initialize ChromaDB client (local persistent vector database)
client = chromadb.PersistentClient(path="./chroma_db")
emb_fn = embedding_functions.DefaultEmbeddingFunction()

collection = client.get_or_create_collection(
    name="recipes",
    embedding_function=emb_fn
)

API_BASE_URL = "https://www.themealdb.com/api/json/v1/1"

def download_image_sync(rid, url, retries=2):
    """Sync download with retries and proxy support."""
    if not url: return None
    ext = url.split('.')[-1] if '.' in url else 'jpg'
    if len(ext) > 4: ext = 'jpg'
    filename = f"{rid}.{ext}"
    local_path = os.path.join(IMAGES_DIR, filename)

    if os.path.exists(local_path):
        return filename

    with httpx.Client(trust_env=True, timeout=10.0) as client_http:
        for attempt in range(retries + 1):
            try:
                logger.info(f"Downloading image locally: {url} (Attempt {attempt+1})")
                with client_http.stream("GET", url, follow_redirects=True) as response:
                    if response.status_code == 200:
                        with open(local_path, 'wb') as f:
                            for chunk in response.iter_bytes():
                                f.write(chunk)
                        return filename
                break
            except Exception as e:
                if attempt == retries:
                    logger.error(f"Failed to download {url} after {retries+1} attempts: {e}")
                else:
                    time.sleep(1)
    return None

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

def estimate_nutrition(title, ingredients):
    """Estimate Calories, Protein, Carbs, Fat for a recipe using LLM."""
    prompt = (
        f"Estimate average Calories, Protein(g), Carbs(g), and Fat(g) for the recipe '{title}' "
        f"based on these ingredients: {json.dumps(ingredients)}. "
        "Return a JSON object where the keys are: calories, protein, carbs, fat. "
        "Ensure values are numbers. Return ONLY JSON."
    )
    try:
        response = litellm.completion(
            model=DEFAULT_MODEL,
            messages=[{"role": "system", "content": "You are a professional dietitian JSON API."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
        return json.loads(content)
    except Exception as e:
        logger.error(f"Nutrition estimation failed for {title}: {e}")
        return {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

def process_meal(meal):
    title = meal.get("strMeal")
    meal_id = meal.get("idMeal")
    if not title or not meal_id:
        return
    
    source_id = f"themealdb_{meal_id}"
    # Avoid duplicates by checking unique source ID instead of title
    existing = collection.get(where={"source": source_id})
    
    if existing['ids']:
        rid = existing['ids'][0]
        meta = existing['metadatas'][0]
        
        needs_update = False
        updates = {}
        
        # Check if we need image
        if not meta.get("image") and meal.get("strMealThumb"):
            logger.info(f"Updating {title} - adding missing image.")
            img_url = meal.get("strMealThumb")
            download_image_sync(rid, img_url)
            updates["image"] = img_url
            needs_update = True
        
        # Check if we need nutrition
        nutri_str = meta.get("nutrition")
        if not nutri_str or json.loads(nutri_str).get("calories", 0) == 0:
            logger.info(f"Updating {title} - adding missing nutrition data.")
            ingredients = get_ingredients(meal)
            nut = estimate_nutrition(title, ingredients)
            updates["nutrition"] = json.dumps(nut)
            needs_update = True
            
        if needs_update:
            new_meta = {**meta, **updates}
            collection.update(ids=[rid], metadatas=[new_meta])
            logger.info(f"Successfully updated metadata for {title}")
        else:
            logger.info(f"Skipping {title} - already complete.")
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
    
    # Estimate nutrition for NEW recipe
    logger.info(f"Estimating nutrition for brand new recipe: {title}")
    nut = estimate_nutrition(title, ingredients)
    
    metadata = {
        "title": title,
        "category": category,
        "area": area,
        "tags": tags if tags else "",
        "ingredients": json.dumps(ingredients),
        "instructions": instructions,
        "source": source_id,
        "image": meal.get("strMealThumb", ""),
        "nutrition": json.dumps(nut)
    }
    
    recipe_id = str(uuid.uuid4())
    img_url = meal.get("strMealThumb", "")
    download_image_sync(recipe_id, img_url)

    collection.add(
        documents=[document],
        metadatas=[metadata],
        ids=[recipe_id]
    )
    logger.info(f"Added {title} ({category}, {area}) with nutrition data.")

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
