import json
import logging
import os
import time
import chromadb
from chromadb.utils import embedding_functions
import litellm

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# STATIC CONFIG
DATA_DIR = "."
DEFAULT_MODEL = "gemini/gemini-2.0-flash"

# Initialize ChromaDB
CHROMA_PATH = os.path.join(DATA_DIR, "chroma_db")
client = chromadb.PersistentClient(path=CHROMA_PATH)
emb_fn = embedding_functions.DefaultEmbeddingFunction()
collection = client.get_or_create_collection(name="recipes", embedding_function=emb_fn)

def estimate_multiple_nutrition(recipes_list):
    """Estimate Calories, Protein, Carbs, Fat for multiple recipes in ONE LLM call."""
    if not recipes_list: return {}
    
    input_data = []
    for r in recipes_list:
        meta = r['metadata']
        input_data.append({
            "id": r["id"], 
            "title": meta.get("title"), 
            "ingredients": json.loads(meta.get("ingredients", "[]"))
        })
        
    prompt = (
        "Estimate average Calories, Protein(g), Carbs(g), and Fat(g) for the following recipes. "
        "Return a JSON object where keys are the recipe IDs and values are objects with keys: calories, protein, carbs, fat. "
        "Return ONLY the JSON object.\n\n"
        "Note: You MUST use the exact recipe IDs provided as keys in the JSON object.\n\n"
        f"Recipes: {json.dumps(input_data)}"
    )

    try:
        response = litellm.completion(
            model=DEFAULT_MODEL,
            messages=[{"role": "system", "content": "You are a professional dietitian JSON API."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        print(f"DEBUG: Raw AI Response Content Snippet: {content[:200]}...")
        
        # Clean potential markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        results = json.loads(content) or {}
        # Ensure all keys are strings (in case the LLM returned integers for ID-like strings)
        processed_results = {str(k): v for k, v in results.items()}
        logger.info(f"Received nutrition results for {len(processed_results)} recipes in this batch.")
        return processed_results
    except Exception as e:
        if "429" in str(e):
            logger.warning("Rate limit hit (429). Waiting 30 seconds...")
            time.sleep(30)
            # Recursively try one more time for this batch
            return estimate_multiple_nutrition(recipes_list)
        logger.error(f"Aggregated nutrition error: {e}")
        return {}

def backfill():
    # 1. Get ALL recipes
    res = collection.get(include=["metadatas"])
    ids = res['ids']
    metas = res['metadatas']
    
    to_process = []
    for i, rid in enumerate(ids):
        meta = metas[i]
        nutri_str = meta.get("nutrition")
        # Process if missing, 0, or the previous "bogus" 500 fallback
        needs_fill = False
        if not nutri_str:
            needs_fill = True
        else:
            try:
                nut = json.loads(nutri_str)
                if nut.get("calories", 0) == 0 or nut.get("calories") == 500:
                    needs_fill = True
            except:
                needs_fill = True
                
        if needs_fill:
            to_process.append({"id": rid, "metadata": meta})
            
    logger.info(f"Found {len(to_process)} recipes needing nutritional backfill.")
    
    # 2. Process in smaller batches with delays to avoid 429 rate limits
    batch_size = 5
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i:i+batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{len(to_process)//batch_size + 1} ({len(batch)} recipes)...")
        
        results = estimate_multiple_nutrition(batch)
        
        for item in batch:
            rid = item["id"]
            meta = item["metadata"]
            if rid in results:
                nut = results[rid]
                new_meta = {**meta, "nutrition": json.dumps(nut)}
                collection.update(ids=[rid], metadatas=[new_meta])
                logger.info(f"Updated {meta.get('title')}: {nut}")
            else:
                logger.warning(f"No nutrition returned for {meta.get('title')}, using zero fallback.")
                fallback = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
                collection.update(ids=[rid], metadatas=[{**meta, "nutrition": json.dumps(fallback)}])
        
        # Polite delay to avoid hitting rate limits too fast
        time.sleep(2)

if __name__ == "__main__":
    backfill()
    logger.info("Backfill complete!")
