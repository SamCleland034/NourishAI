"""
Ingest Spoonacular recipes into Pinecone.

Free tier: 150 points/day at spoonacular.com/food-api/console
  - complexSearch with addRecipeInformation + addRecipeNutrition costs ~1 pt/recipe
  - Default batch of 100/run is conservative; raise with --batch-size if you have quota

Nutrition comes directly from Spoonacular — no LLM estimation needed.

Progress is saved to spoonacular_progress.json so re-runs pick up where they left off.
Delete that file to start over from the beginning.

Usage:
    python ingest_spoonacular.py                       # 100 recipes, cuisine mix
    python ingest_spoonacular.py --batch-size 50       # smaller daily run
    python ingest_spoonacular.py --cuisine Italian     # single cuisine
    python ingest_spoonacular.py --reset               # clear progress and restart
"""

import os
import json
import uuid
import time
import logging
import argparse

import httpx
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- CONFIG ---
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")
PINECONE_API_KEY    = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "recipes")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL     = "text-embedding-3-small"
DIMENSION           = 1536

SPOONACULAR_SEARCH  = "https://api.spoonacular.com/recipes/complexSearch"
PROGRESS_FILE       = "spoonacular_progress.json"

# Cuisines to cycle through for variety — Spoonacular recognises all of these
CUISINES = [
    "African", "Asian", "American", "British", "Cajun", "Caribbean",
    "Chinese", "Eastern European", "European", "French", "German",
    "Greek", "Indian", "Irish", "Italian", "Japanese", "Jewish",
    "Korean", "Latin American", "Mediterranean", "Mexican", "Middle Eastern",
    "Nordic", "Southern", "Spanish", "Thai", "Vietnamese",
]

# --- CLIENTS ---
oa_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
pc        = Pinecone(api_key=PINECONE_API_KEY) if PINECONE_API_KEY else None


# ---------------------------------------------------------------------------
# Pinecone
# ---------------------------------------------------------------------------

def get_or_create_index():
    if not pc:
        raise RuntimeError("PINECONE_API_KEY is not set.")
    existing = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing:
        logger.info(f"Creating Pinecone index '{PINECONE_INDEX_NAME}' (dim={DIMENSION})…")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(PINECONE_INDEX_NAME)


def get_embedding(text: str) -> list:
    if not oa_client:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    res = oa_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
    return res.data[0].embedding


# ---------------------------------------------------------------------------
# Progress tracking (resume across daily runs)
# ---------------------------------------------------------------------------

def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    # cuisine_index tracks which cuisine we're currently fetching
    # offset tracks how far into that cuisine we've paginated
    return {"cuisine_index": 0, "offset": 0, "total_ingested": 0}


def save_progress(state: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Spoonacular API
# ---------------------------------------------------------------------------

def search_recipes(cuisine: str, offset: int, number: int) -> dict:
    params = {
        "apiKey":                 SPOONACULAR_API_KEY,
        "cuisine":                cuisine,
        "number":                 number,
        "offset":                 offset,
        "addRecipeInformation":   True,
        "addRecipeNutrition":     True,
        "instructionsRequired":   True,   # skip recipes with no instructions
        "fillIngredients":        True,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.get(SPOONACULAR_SEARCH, params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def extract_nutrition(nutrients: list) -> dict:
    lookup = {n["name"].lower(): n["amount"] for n in nutrients}
    return {
        "calories": round(lookup.get("calories", 0), 1),
        "protein":  round(lookup.get("protein", 0), 1),
        "carbs":    round(lookup.get("carbohydrates", 0), 1),
        "fat":      round(lookup.get("fat", 0), 1),
    }


def extract_ingredients(extended: list) -> list[dict]:
    result = []
    for ing in extended:
        amount = ing.get("amount", "")
        unit   = ing.get("unit", "")
        qty    = f"{amount} {unit}".strip() if amount else ""
        item   = ing.get("name") or ing.get("original") or ""
        if item:
            result.append({"qty": str(qty), "item": item.strip()})
    return result


def extract_instructions(analyzed: list) -> str:
    parts = []
    for block in analyzed:
        for step in block.get("steps", []):
            num  = step.get("number", len(parts) + 1)
            text = step.get("step", "").strip()
            if text:
                parts.append(f"{num}. {text}")
    return "\n".join(parts)


def normalise_recipe(item: dict) -> dict | None:
    title = item.get("title", "").strip()
    if not title:
        return None

    # Instructions
    analyzed = item.get("analyzedInstructions") or []
    instructions = extract_instructions(analyzed)
    if not instructions:
        return None

    # Ingredients
    extended    = item.get("extendedIngredients") or []
    ingredients = extract_ingredients(extended)
    if not ingredients:
        return None

    # Category: dishTypes like ["lunch", "main course"] → title-case first entry
    dish_types = item.get("dishTypes") or []
    category   = dish_types[0].title() if dish_types else "Miscellaneous"

    # Area: cuisines like ["Italian", "European"] → first entry
    cuisines = item.get("cuisines") or []
    area     = cuisines[0] if cuisines else "International"

    # Tags: diets like ["gluten free", "vegan"] + any extra tags
    diets = item.get("diets") or []
    tags  = ", ".join(diets)

    # Image
    image = item.get("image") or ""

    # Nutrition — comes directly from Spoonacular, no LLM needed
    nutrients_raw = (item.get("nutrition") or {}).get("nutrients") or []
    nutrition = extract_nutrition(nutrients_raw)

    return {
        "spoonacular_id": str(item["id"]),
        "title":          title,
        "category":       category,
        "area":           area,
        "tags":           tags,
        "ingredients":    ingredients,
        "instructions":   instructions,
        "image":          image,
        "nutrition":      nutrition,
    }


# ---------------------------------------------------------------------------
# Ingest one recipe
# ---------------------------------------------------------------------------

def ingest_recipe(index, recipe: dict) -> bool:
    source_id = f"spoonacular_{recipe['spoonacular_id']}"
    recipe_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_id))  # deterministic → idempotent

    try:
        existing = index.fetch(ids=[recipe_id])
        if existing.get("vectors") and recipe_id in existing["vectors"]:
            logger.info(f"  skip (exists): {recipe['title']}")
            return False
    except Exception:
        pass

    ingredients_str = ", ".join(
        f"{i['qty']} {i['item']}".strip() for i in recipe["ingredients"]
    )
    document = (
        f"RECIPE TITLE: {recipe['title']}\n"
        f"CATEGORY: {recipe['category']}\n"
        f"AREA: {recipe['area']}\n"
        f"TAGS: {recipe['tags']}\n"
        f"INGREDIENTS: {ingredients_str}\n"
        f"INSTRUCTIONS: {recipe['instructions']}"
    )

    metadata = {
        "title":        recipe["title"],
        "category":     recipe["category"],
        "area":         recipe["area"],
        "tags":         recipe["tags"],
        "ingredients":  json.dumps(recipe["ingredients"]),
        "instructions": recipe["instructions"],
        "source":       source_id,
        "image":        recipe["image"],
        "nutrition":    json.dumps(recipe["nutrition"]),
    }

    embedding = get_embedding(document)
    index.upsert(vectors=[{"id": recipe_id, "values": embedding, "metadata": metadata}])
    logger.info(f"  ingested: {recipe['title']} ({recipe['category']}, {recipe['area']})")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def ingest_all(batch_size: int = 100, cuisine_filter: str = None, reset: bool = False):
    if not SPOONACULAR_API_KEY:
        logger.error("SPOONACULAR_API_KEY is not set. Get a free key at spoonacular.com/food-api/console")
        return

    if reset and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        logger.info("Progress reset.")

    index    = get_or_create_index()
    state    = load_progress()
    cuisines = [cuisine_filter] if cuisine_filter else CUISINES

    ingested = skipped = errors = 0
    remaining = batch_size

    while remaining > 0:
        ci     = state["cuisine_index"] % len(cuisines)
        cuisine = cuisines[ci]
        offset  = state["offset"]

        fetch_n = min(remaining, 100)  # Spoonacular max per request is 100
        logger.info(f"Fetching {fetch_n} recipes — cuisine: {cuisine}, offset: {offset}…")

        try:
            data         = search_recipes(cuisine, offset, fetch_n)
            results      = data.get("results") or []
            total_avail  = data.get("totalResults", 0)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 402:
                logger.error("Spoonacular daily quota exhausted (402). Run again tomorrow.")
            else:
                logger.error(f"HTTP error: {e}")
            break
        except Exception as e:
            logger.error(f"Request failed: {e}")
            break

        if not results:
            # Move to next cuisine
            logger.info(f"  no results for {cuisine} at offset {offset} — moving to next cuisine.")
            state["cuisine_index"] += 1
            state["offset"]         = 0
            save_progress(state)
            continue

        for item in results:
            try:
                recipe = normalise_recipe(item)
                if recipe:
                    added = ingest_recipe(index, recipe)
                    if added:
                        ingested += 1
                        state["total_ingested"] += 1
                    else:
                        skipped += 1
                else:
                    errors += 1
            except Exception as e:
                logger.error(f"  error processing '{item.get('title', '?')}': {e}")
                errors += 1

        remaining              -= len(results)
        state["offset"]         = offset + len(results)

        # If we've exhausted this cuisine, move to the next
        if state["offset"] >= total_avail:
            logger.info(f"  finished cuisine: {cuisine} ({total_avail} total available).")
            state["cuisine_index"] += 1
            state["offset"]         = 0

        save_progress(state)
        time.sleep(0.5)  # be polite

    logger.info(
        f"Run complete — ingested: {ingested}, skipped: {skipped}, errors: {errors}. "
        f"All-time total: {state['total_ingested']}"
    )
    try:
        logger.info(f"Index stats: {index.describe_index_stats()}")
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Spoonacular recipes into Pinecone")
    parser.add_argument("--batch-size",  type=int,   default=100,  help="Recipes to fetch this run (default: 100)")
    parser.add_argument("--cuisine",     type=str,   default=None, help="Restrict to one cuisine (default: cycle through all)")
    parser.add_argument("--reset",       action="store_true",      help="Clear saved progress and restart from the beginning")
    args = parser.parse_args()

    ingest_all(batch_size=args.batch_size, cuisine_filter=args.cuisine, reset=args.reset)
