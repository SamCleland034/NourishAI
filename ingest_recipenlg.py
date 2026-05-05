"""
Ingest corbt/all-recipes dataset (~125K AllRecipes) from HuggingFace into Pinecone.

No API key, no rate limits, no daily quota — runs once and ingests as many
recipes as you want.

Install the extra dependency first:
    pip install datasets        (or: uv add datasets)

Usage:
    python ingest_recipenlg.py                        # ingest 5,000 recipes
    python ingest_recipenlg.py --limit 20000          # ingest 20,000
    python ingest_recipenlg.py --limit 0              # ingest everything (~125K)
    python ingest_recipenlg.py --with-nutrition       # also estimate nutrition via LLM (uses Gemini quota)
    python ingest_recipenlg.py --reset                # clear progress and restart

The dataset is streamed — it does not download all records at once.
Progress is saved to recipenlg_progress.json so runs can be resumed.
"""

import os
import json
import uuid
import time
import logging
import argparse
import re
import litellm
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from datasets import load_dataset
except ImportError:
    raise SystemExit(
        "The 'datasets' package is required.\n"
        "Install with:  pip install datasets   or   uv add datasets"
    )

# --- CONFIG ---
PINECONE_API_KEY    = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "recipes")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL     = "text-embedding-3-small"
DIMENSION           = 1536
DEFAULT_MODEL       = "gemini/gemini-2.0-flash"
PROGRESS_FILE       = "allrecipes_progress.json"
UPSERT_BATCH        = 50   # vectors per Pinecone upsert call
NUTRITION_BATCH     = 20   # recipes per LLM nutrition call

if not os.getenv("GEMINI_API_KEY") and os.getenv("GOOGLE_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")

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
        logger.info(f"Creating Pinecone index '{PINECONE_INDEX_NAME}'…")
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
# Progress
# ---------------------------------------------------------------------------

def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"skipped": 0, "total_ingested": 0}


def save_progress(state: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Nutrition estimation (optional — batched to save LLM quota)
# ---------------------------------------------------------------------------

def estimate_nutrition_batch(recipes: list[dict]) -> dict:
    """
    Estimate nutrition for multiple recipes in one LLM call.
    Returns {recipe_id: {calories, protein, carbs, fat}}.
    """
    input_data = [
        {"id": r["_tmp_id"], "title": r["title"], "ingredients": r["ingredients"]}
        for r in recipes
    ]
    prompt = (
        "Estimate average Calories, Protein(g), Carbs(g), and Fat(g) for each recipe below. "
        "Return a JSON object where keys are the recipe IDs and values are objects with keys: "
        "calories, protein, carbs, fat (all numbers). Return ONLY the raw JSON object.\n\n"
        f"Recipes: {json.dumps(input_data)}"
    )
    try:
        resp = litellm.completion(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional dietitian JSON API."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        if "```" in content:
            content = content.split("```")[1].lstrip("json").strip().rstrip("```").strip()
        return json.loads(content)
    except Exception as e:
        logger.warning(f"Batch nutrition estimation failed: {e}")
        return {r["_tmp_id"]: {"calories": 0, "protein": 0, "carbs": 0, "fat": 0} for r in recipes}


# ---------------------------------------------------------------------------
# Dataset normalisation
# ---------------------------------------------------------------------------

# RecipeNLG source names → friendly category labels
SOURCE_CATEGORY_MAP = {
    "Gathered": "Miscellaneous",
    "Recipes1M": "Miscellaneous",
}

# Simple keyword → category heuristic applied to recipe title
TITLE_CATEGORY_HINTS = [
    (["cake", "cookie", "brownie", "muffin", "pie", "tart", "pudding", "fudge",
      "biscuit", "scone", "dessert", "sweet", "chocolate", "vanilla"], "Dessert"),
    (["soup", "stew", "chowder", "bisque", "broth"], "Soup"),
    (["salad", "slaw"], "Side"),
    (["bread", "roll", "loaf", "bun", "muffin"], "Bread"),
    (["pasta", "noodle", "spaghetti", "fettuccine", "lasagna", "linguine"], "Pasta"),
    (["chicken", "poultry", "turkey"], "Chicken"),
    (["beef", "steak", "burger", "meatball", "meatloaf"], "Beef"),
    (["pork", "bacon", "ham", "sausage"], "Pork"),
    (["fish", "salmon", "tuna", "shrimp", "prawn", "seafood", "crab", "lobster"], "Seafood"),
    (["lamb", "mutton"], "Lamb"),
    (["vegetarian", "vegan", "tofu", "tempeh", "lentil", "chickpea", "bean"], "Vegetarian"),
    (["breakfast", "pancake", "waffle", "omelette", "oatmeal", "granola"], "Breakfast"),
    (["smoothie", "juice", "cocktail", "drink", "lemonade"], "Starter"),
]

def guess_category(title: str) -> str:
    tl = title.lower()
    for keywords, cat in TITLE_CATEGORY_HINTS:
        if any(kw in tl for kw in keywords):
            return cat
    return "Miscellaneous"


# Regex to split ingredient list items on the "- " bullet pattern
_ING_BULLET_RE = re.compile(r'\s*-\s+')

# Matches a leading quantity token: "2 cups", "1/2 tsp", "¾ oz", bare number, etc.
_QTY_RE = re.compile(
    r"^([\d¼½¾⅓⅔⅛⅜⅝⅞/\-.]+\s*"
    r"(?:cups?|tbsp|tsp|tablespoons?|teaspoons?|oz|lbs?|g|kg|ml|l|"
    r"cloves?|cans?|slices?|pieces?|bunches?|sprigs?|pinch|handful|"
    r"packages?|pkg|strips?|heads?|ears?|inches?|cm|mm|"
    r"large|medium|small|whole)?)\s+(.+)$",
    re.IGNORECASE,
)


def normalise_ingredients(raw: list[str]) -> list[dict]:
    """Split each raw ingredient string into {qty, item}."""
    result = []
    for text in raw:
        text = text.strip()
        if not text:
            continue
        m = _QTY_RE.match(text)
        if m:
            result.append({"qty": m.group(1).strip(), "item": m.group(2).strip()})
        else:
            result.append({"qty": "", "item": text})
    return result


def normalise_row(row: dict) -> dict | None:
    """
    Parse the dataset's single 'input' field which has the format:
        {Title}  Ingredients: - ing1 - ing2 ... Directions: step1 step2 ...
    """
    text = (row.get("input") or "").strip()
    if not text or "Ingredients:" not in text:
        return None

    # ---- Title ----
    title, body = text.split("Ingredients:", 1)
    title = title.strip()
    if not title:
        return None

    # ---- Ingredients / Directions split ----
    dir_marker = None
    for marker in ("Directions:", "Instructions:", "Steps:", "Method:"):
        if marker in body:
            dir_marker = marker
            break

    if dir_marker:
        ing_text, dir_text = body.split(dir_marker, 1)
    else:
        ing_text, dir_text = body, ""

    # ---- Parse ingredients ----
    raw_ings = [s.strip() for s in _ING_BULLET_RE.split(ing_text) if s.strip()]
    ingredients = normalise_ingredients(raw_ings)   # splits qty from item name
    if not ingredients:
        return None

    # ---- Parse instructions ----
    dir_text = dir_text.strip()
    if dir_text:
        # Try numbered steps first ("1. ...", "2. ...")
        steps = re.split(r'\s*\d+\.\s+', dir_text)
        steps = [s.strip() for s in steps if s.strip()]
        if len(steps) > 1:
            instructions = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        else:
            instructions = dir_text
    else:
        # No directions section — build a basic instruction from ingredients
        instructions = "Combine all ingredients and prepare according to standard method."

    return {
        "title":        title,
        "category":     guess_category(title),
        "area":         "International",
        "tags":         "",
        "ingredients":  ingredients,
        "instructions": instructions,
        "image":        "",
        "source_key":   title,   # title is the only stable identifier in this dataset
    }


# ---------------------------------------------------------------------------
# Main ingest loop
# ---------------------------------------------------------------------------

def ingest_all(limit: int = 5000, with_nutrition: bool = False, reset: bool = False):
    if reset and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        logger.info("Progress reset.")

    index = get_or_create_index()
    state = load_progress()

    already_done = state["total_ingested"] + state["skipped"]
    logger.info(
        f"Loading RecipeNLG dataset (streaming)… "
        f"resuming from position ~{already_done}"
    )

    ds = load_dataset("corbt/all-recipes", split="train", streaming=True)
    ds = ds.skip(already_done)

    ingested = skipped = errors = 0
    queued = 0   # recipes successfully embedded and queued — this is what --limit counts
    pending_vectors: list[dict] = []
    pending_nutrition: list[dict] = []

    for row in ds:
        if limit and queued >= limit:
            break

        recipe = normalise_row(row)
        if not recipe:
            errors += 1
            continue

        source_id = f"allrecipes_{str(uuid.uuid5(uuid.NAMESPACE_URL, recipe['source_key']))}"
        recipe_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_id))

        try:
            existing = index.fetch(ids=[recipe_id])
            if existing.get("vectors") and recipe_id in existing["vectors"]:
                skipped += 1
                continue
        except Exception:
            pass

        ingredients_str = ", ".join(
            f"{i['qty']} {i['item']}".strip() for i in recipe["ingredients"]
        )
        document = (
            f"RECIPE TITLE: {recipe['title']}\n"
            f"CATEGORY: {recipe['category']}\n"
            f"AREA: {recipe['area']}\n"
            f"INGREDIENTS: {ingredients_str}\n"
            f"INSTRUCTIONS: {recipe['instructions']}"
        )

        try:
            embedding = get_embedding(document)
        except Exception as e:
            logger.error(f"Embedding failed for '{recipe['title']}': {e}")
            errors += 1
            continue

        recipe["_tmp_id"]    = recipe_id
        recipe["_embedding"] = embedding
        recipe["_source_id"] = source_id

        if with_nutrition:
            pending_nutrition.append(recipe)

        pending_vectors.append(recipe)
        queued += 1

        # Flush nutrition batch
        if with_nutrition and len(pending_nutrition) >= NUTRITION_BATCH:
            nutrition_map = estimate_nutrition_batch(pending_nutrition)
            for r in pending_nutrition:
                r["_nutrition"] = nutrition_map.get(r["_tmp_id"], {"calories": 0, "protein": 0, "carbs": 0, "fat": 0})
            pending_nutrition = []

        # Flush upsert batch
        if len(pending_vectors) >= UPSERT_BATCH:
            batch_count = len(pending_vectors)
            _flush(index, pending_vectors, with_nutrition)
            ingested += batch_count
            pending_vectors = []
            state["total_ingested"] = state.get("total_ingested", 0) + batch_count
            state["skipped"]        = skipped
            save_progress(state)
            logger.info(f"  progress: {state['total_ingested']} ingested total")

    # Flush nutrition remainder
    if with_nutrition and pending_nutrition:
        nutrition_map = estimate_nutrition_batch(pending_nutrition)
        for r in pending_nutrition:
            r["_nutrition"] = nutrition_map.get(r["_tmp_id"], {"calories": 0, "protein": 0, "carbs": 0, "fat": 0})

    # Flush vector remainder
    if pending_vectors:
        _flush(index, pending_vectors, with_nutrition)
        ingested += len(pending_vectors)

    state["total_ingested"] = state.get("total_ingested", 0) + ingested
    state["skipped"]        = state.get("skipped", 0) + skipped
    save_progress(state)

    logger.info(f"Done — ingested: {ingested}, skipped: {skipped}, errors: {errors}")
    logger.info(f"All-time total: {state['total_ingested']}")
    try:
        logger.info(f"Index stats: {index.describe_index_stats()}")
    except Exception:
        pass


def _flush(index, recipes: list[dict], with_nutrition: bool):
    """Upsert a batch of prepared recipe dicts into Pinecone."""
    vectors = []
    for recipe in recipes:
        nutrition = recipe.get("_nutrition") or {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
        metadata = {
            "title":        recipe["title"],
            "category":     recipe["category"],
            "area":         recipe["area"],
            "tags":         recipe["tags"],
            "ingredients":  json.dumps(recipe["ingredients"]),
            "instructions": recipe["instructions"],
            "source":       recipe["_source_id"],
            "image":        recipe["image"],
            "nutrition":    json.dumps(nutrition),
        }
        vectors.append({
            "id":       recipe["_tmp_id"],
            "values":   recipe["_embedding"],
            "metadata": metadata,
        })
    index.upsert(vectors=vectors)
    logger.info(f"  upserted batch of {len(vectors)}")


def peek():
    """Print the first 3 rows of the dataset so we can see the real field names."""
    print("Loading dataset (streaming)…")
    ds = load_dataset("corbt/all-recipes", split="train", streaming=True)
    for i, row in enumerate(ds):
        print(f"\n--- Row {i} keys: {list(row.keys())} ---")
        for k, v in row.items():
            snippet = str(v)[:120].replace("\n", " ")
            print(f"  {k!r:30s}: {snippet}")
        if i >= 2:
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest AllRecipes dataset into Pinecone")
    parser.add_argument("--peek",            action="store_true",
                        help="Print the first 3 rows and exit (use this to inspect field names)")
    parser.add_argument("--limit",           type=int,            default=5000,
                        help="Max recipes to ingest this run (0 = all, default: 5000)")
    parser.add_argument("--with-nutrition",  action="store_true",
                        help="Estimate nutrition via LLM (uses Gemini quota, ~1 call per 20 recipes)")
    parser.add_argument("--reset",           action="store_true",
                        help="Clear saved progress and restart from the beginning")
    args = parser.parse_args()

    if args.peek:
        peek()
    else:
        ingest_all(
            limit=args.limit if args.limit > 0 else None,
            with_nutrition=args.with_nutrition,
            reset=args.reset,
        )
