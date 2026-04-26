import json
import uuid
import os
import logging
import chromadb
from chromadb.utils import embedding_functions
import litellm
import argparse
import httpx

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# STATIC CONFIG
IMAGES_DIR = os.path.join("static", "recipe_images")
os.makedirs(IMAGES_DIR, exist_ok=True)

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

def generate_llm_recipe(model="gemini/gemini-2.0-flash"):
    """Generates a creative recipe using LiteLLM (supports OpenAI, Anthropic, Gemini, etc.)."""
    
    prompt = """
    Generate a creative, high-quality, and realistic cooking recipe.
    The response MUST be a valid JSON object matching TheMealDB API format.
    
    Fields required:
    - idMeal: A random 5-digit string.
    - strMeal: A unique and appetizing name for the dish.
    - strCategory: Choose one from [Beef, Chicken, Dessert, Lamb, Miscellaneous, Pasta, Pork, Seafood, Side, Starter, Vegan, Vegetarian].
    - strArea: The cuisine or origin (e.g., Italian, Japanese, Moroccan, Fusion).
    - strInstructions: Clear, numbered, step-by-step cooking instructions.
    - strMealThumb: "https://placehold.co/500"
    - strTags: A comma-separated list of relevant tags.
    - strIngredient1 through strIngredient20: The names of the ingredients.
    - strMeasure1 through strMeasure20: The measurements for each ingredient.

    Fill unused ingredient/measure fields with empty strings.
    Return ONLY the raw JSON object.
    """

    logger.info(f"Requesting recipe using LiteLLM (Model: {model})...")
    
    # litellm.completion handles different providers based on the model prefix
    # e.g., "anthropic/claude-3", "gemini/gemini-pro", "gpt-4o"
    response = litellm.completion(
        model=model,
        messages=[{"role": "system", "content": "You are a professional chef and data engineer specialized in JSON output."},
                  {"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content
    # Some models might wrap JSON in markdown blocks
    if content.startswith("```json"):
        content = content.replace("```json", "").replace("```", "").strip()
        
    meal = json.loads(content)
    return meal

def ingest_to_chroma(meal):
    """Embeds and stores the recipe in ChromaDB."""
    client = chromadb.PersistentClient(path="./chroma_db")
    emb_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_name="text-embedding-3-small"
    )
    collection = client.get_or_create_collection(name="recipes", embedding_function=emb_fn)
    
    # Extract ingredients
    ingredients_list = []
    for i in range(1, 21):
        ing = meal.get(f"strIngredient{i}")
        meas = meal.get(f"strMeasure{i}")
        if ing and ing.strip(): 
            ingredients_list.append({"item": ing.strip(), "qty": meas.strip() if meas else "1"})
    
    ingredients_str = ", ".join([f"{i['qty']} {i['item']}" for i in ingredients_list])
    
    document = f"""
    RECIPE TITLE: {meal['strMeal']}
    CATEGORY: {meal['strCategory']}
    AREA: {meal['strArea']}
    TAGS: {meal.get('strTags', '')}
    INGREDIENTS: {ingredients_str}
    INSTRUCTIONS: {meal['strInstructions']}
    """
    
    recipe_id = str(uuid.uuid4())
    img_url = meal.get('strMealThumb', '')
    filename = download_image_sync(recipe_id, img_url)
    
    metadata = {
        "title": meal['strMeal'],
        "category": meal['strCategory'],
        "area": meal['strArea'],
        "tags": meal.get('strTags', ''),
        "ingredients": json.dumps(ingredients_list),
        "instructions": meal['strInstructions'],
        "source": f"llm_synthetic_{meal.get('idMeal', uuid.uuid4().hex[:5])}",
        "image": filename if filename else img_url
    }

    collection.add(
        documents=[document],
        metadatas=[metadata],
        ids=[recipe_id]
    )
    logger.info(f"Successfully Ingested: {meal['strMeal']} ({meal['strArea']})")

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic recipes using LiteLLM (Multi-Provider)")
    parser.add_argument("--count", type=int, default=1, help="Number of recipes to generate")
    parser.add_argument("--model", type=str, default="gemini/gemini-2.0-flash", 
                        help="Model to use (e.g., 'gpt-4o', 'anthropic/claude-3-5-sonnet-20240620', 'gemini/gemini-1.5-pro')")
    parser.add_argument("--save-json", action="store_true", help="Save to JSON file instead of DB")
    
    args = parser.parse_args()

    synthetic_meals = []
    for i in range(args.count):
        try:
            meal = generate_llm_recipe(model=args.model)
            if args.save_json:
                synthetic_meals.append(meal)
            else:
                ingest_to_chroma(meal)
        except Exception as e:
            logger.error(f"Failed to generate recipe {i+1}: {e}")
            
    if args.save_json and synthetic_meals:
        with open("llm_recipes.json", "w") as f:
            json.dump({"meals": synthetic_meals}, f, indent=2)
        print(f"✅ Saved {len(synthetic_meals)} recipes to llm_recipes.json")

if __name__ == "__main__":
    main()
