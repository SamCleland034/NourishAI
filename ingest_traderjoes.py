"""
Ingest Trader Joe's recipes into Pinecone.

TJ's entire site is behind Cloudflare, so regular httpx/requests calls return 403.
This script uses `curl_cffi` to impersonate Chrome's TLS fingerprint and bypass it.

Install the extra dependency before running:
    pip install curl_cffi        (or: uv add curl_cffi)

Discovery strategy (in order):
  1. TJ's sitemap (https://www.traderjoes.com/sitemap.xml)
  2. Recipe listing page with pagination (/home/recipes?page=N) — href scraping
  3. __NEXT_DATA__ JSON embedded by Next.js on the listing page

Per-recipe extraction:
  1. recipe-scrapers (schema.org / ld+json)
  2. __NEXT_DATA__ JSON fallback

Usage:
    python ingest_traderjoes.py                   # all recipes
    python ingest_traderjoes.py --max-recipes 10  # quick test
    python ingest_traderjoes.py --delay 2.0       # slower / more polite
"""

import os
import re
import json
import uuid
import time
import logging
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import litellm
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- curl_cffi: required for Cloudflare bypass ---
try:
    from curl_cffi import requests as cf
    IMPERSONATE = "chrome124"
    logger.info("curl_cffi available — Cloudflare bypass enabled.")
except ImportError:
    cf = None
    logger.error(
        "curl_cffi is not installed. Trader Joe's site is behind Cloudflare and will "
        "return 403 without it.\n"
        "Install with:  pip install curl_cffi   or   uv add curl_cffi"
    )

from recipe_scrapers import scrape_me, WebsiteNotImplementedError

# --- CONFIG ---
DEFAULT_MODEL = "gemini/gemini-2.5-flash"
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "recipes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"
DIMENSION = 1536

TJ_BASE = "https://www.traderjoes.com"
TJ_SITEMAP = f"{TJ_BASE}/sitemap.xml"
TJ_RECIPES_PAGE = f"{TJ_BASE}/home/recipes"
TJ_RECIPE_PATH = "/home/recipes/"

# LiteLLM alias
if not os.getenv("GEMINI_API_KEY") and os.getenv("GOOGLE_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# --- CLIENTS ---
oa_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
pc = Pinecone(api_key=PINECONE_API_KEY) if PINECONE_API_KEY else None

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>',
    re.DOTALL,
)
HREF_RECIPE_RE = re.compile(r'href=["\'](' + re.escape(TJ_RECIPE_PATH) + r'[^"\'?#]+)["\']')


# ---------------------------------------------------------------------------
# HTTP (Cloudflare-safe)
# ---------------------------------------------------------------------------

def fetch(url: str, timeout: int = 20) -> str | None:
    """Fetch a URL, bypassing Cloudflare via curl_cffi if available."""
    if cf is None:
        logger.error("curl_cffi not installed — cannot fetch TJ's pages.")
        return None
    try:
        resp = cf.get(url, impersonate=IMPERSONATE, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"fetch failed ({url}): {e}")
        return None


# ---------------------------------------------------------------------------
# Pinecone helpers
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
# Nutrition estimation
# ---------------------------------------------------------------------------

def estimate_nutrition(title: str, ingredients: list) -> dict:
    prompt = (
        f"Estimate average Calories, Protein(g), Carbs(g), Fat(g) for '{title}' "
        f"given ingredients: {json.dumps(ingredients)}. "
        "Return ONLY a JSON object: {calories, protein, carbs, fat} (numbers)."
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
        logger.warning(f"Nutrition estimation failed for '{title}': {e}")
        return {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}


# ---------------------------------------------------------------------------
# Ingredient normalisation
# ---------------------------------------------------------------------------

_QTY_RE = re.compile(
    r"^([\d¼½¾⅓⅔⅛⅜⅝⅞/\-.]+\s*"
    r"(?:cups?|tbsp|tsp|tablespoons?|teaspoons?|oz|lbs?|g|kg|ml|l|"
    r"cloves?|cans?|slices?|pieces?|bunches?|sprigs?|pinch|handful|"
    r"packages?|pkg|strips?|heads?|ears?|inches?|cm|mm|"
    r"large|medium|small|whole)?)\s+(.+)$",
    re.IGNORECASE,
)


def normalise_ingredients(raw: list[str]) -> list[dict]:
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


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------

def _sitemap_urls_from_html(html: str) -> list[str]:
    """Parse sitemap XML and return all URLs that are recipe pages."""
    try:
        root = ET.fromstring(html)
    except ET.ParseError:
        return []

    urls = []
    if "sitemapindex" in root.tag:
        for sitemap_elem in root.findall(f"{{{SITEMAP_NS}}}sitemap"):
            loc = sitemap_elem.find(f"{{{SITEMAP_NS}}}loc")
            if loc is not None and loc.text:
                sub_html = fetch(loc.text.strip())
                if sub_html:
                    urls.extend(_sitemap_urls_from_html(sub_html))
    else:
        for url_elem in root.findall(f"{{{SITEMAP_NS}}}url"):
            loc = url_elem.find(f"{{{SITEMAP_NS}}}loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
    return urls


def _recipe_hrefs_from_html(html: str) -> list[str]:
    """Extract all /home/recipes/<slug> hrefs found in a page's HTML."""
    found = HREF_RECIPE_RE.findall(html)
    # Strip any trailing slashes and deduplicate
    seen = set()
    result = []
    for path in found:
        path = path.rstrip("/")
        full = TJ_BASE + path
        if full not in seen and path != TJ_RECIPE_PATH.rstrip("/"):
            seen.add(full)
            result.append(full)
    return result


def _recipe_urls_from_next_data(html: str) -> list[str]:
    """Try to find recipe slugs from __NEXT_DATA__ on the listing page."""
    m = NEXT_DATA_RE.search(html)
    if not m:
        return []
    try:
        nd = json.loads(m.group(1))
    except Exception:
        return []

    page_props = (nd.get("props") or {}).get("pageProps") or {}
    # Try common keys
    recipes_data = (
        page_props.get("recipes")
        or page_props.get("data")
        or page_props.get("items")
        or []
    )
    if not isinstance(recipes_data, list):
        recipes_data = []

    urls = []
    for item in recipes_data:
        attrs = item.get("attributes") or item
        slug = attrs.get("slug") or attrs.get("url_key") or ""
        if slug:
            urls.append(f"{TJ_RECIPES_PAGE}/{slug}")
    return urls


def get_recipe_urls() -> list[str]:
    """Discover all TJ recipe page URLs using multiple strategies."""
    all_urls: list[str] = []

    # Strategy 1: sitemap
    logger.info("Strategy 1: fetching sitemap…")
    sitemap_html = fetch(TJ_SITEMAP)
    if sitemap_html:
        sitemap_urls = _sitemap_urls_from_html(sitemap_html)
        recipe_urls = [
            u for u in sitemap_urls
            if TJ_RECIPE_PATH in u and u.rstrip("/") != TJ_RECIPES_PAGE.rstrip("/")
        ]
        if recipe_urls:
            logger.info(f"  found {len(recipe_urls)} recipe URLs via sitemap.")
            return recipe_urls

    # Strategy 2: paginate the listing page, collect href links
    logger.info("Strategy 2: scraping recipe listing pages…")
    seen: set[str] = set()
    for page in range(1, 50):  # cap at 50 pages
        url = TJ_RECIPES_PAGE if page == 1 else f"{TJ_RECIPES_PAGE}?page={page}"
        html = fetch(url)
        if not html:
            break

        # Try __NEXT_DATA__ first for this page
        nd_urls = _recipe_urls_from_next_data(html)
        page_urls = nd_urls or _recipe_hrefs_from_html(html)

        new = [u for u in page_urls if u not in seen]
        if not new:
            logger.info(f"  page {page}: no new URLs found — stopping pagination.")
            break

        for u in new:
            seen.add(u)
            all_urls.append(u)
        logger.info(f"  page {page}: +{len(new)} URLs (total {len(all_urls)})")
        time.sleep(1.0)

    if all_urls:
        logger.info(f"Found {len(all_urls)} recipe URLs via listing pages.")
        return all_urls

    logger.error(
        "Could not discover any recipe URLs.\n"
        "  — Check that curl_cffi is installed and up to date.\n"
        "  — TJ's site structure may have changed; inspect a recipe page manually."
    )
    return []


# ---------------------------------------------------------------------------
# Per-recipe scraping
# ---------------------------------------------------------------------------

def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _scrape_via_recipe_scrapers(url: str, html: str) -> dict | None:
    try:
        s = scrape_me(url, html=html, wild_mode=True)
        title = s.title()
        ingredients_raw = s.ingredients()
        if not title or not ingredients_raw:
            return None
        instr = s.instructions()
        return {
            "title": title,
            "ingredients_raw": ingredients_raw,
            "instructions": instr if isinstance(instr, str) else "\n".join(instr),
            "image": _safe(s.image) or "",
            "category": _safe(s.category) or "Miscellaneous",
            "cuisine": _safe(s.cuisine) or "American",
            "tags": _safe(s.keywords) or "",
        }
    except (WebsiteNotImplementedError, Exception) as e:
        logger.debug(f"recipe-scrapers failed for {url}: {e}")
        return None


def _scrape_via_next_data(html: str) -> dict | None:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        nd = json.loads(m.group(1))
    except Exception:
        return None

    page_props = (nd.get("props") or {}).get("pageProps") or {}
    raw = (
        page_props.get("recipe")
        or page_props.get("data")
        or page_props.get("content")
        or {}
    )
    if isinstance(raw, dict) and "attributes" in raw:
        raw = raw["attributes"]

    title = raw.get("title") or raw.get("name") or ""
    if not title:
        return None

    # Ingredients
    ing_raw = raw.get("ingredients") or raw.get("recipe_ingredients") or []
    if isinstance(ing_raw, str) and "<" in ing_raw:
        ing_raw = _li_items(ing_raw)
    elif isinstance(ing_raw, list):
        ing_raw = [
            (i if isinstance(i, str) else i.get("name") or i.get("text") or str(i))
            for i in ing_raw
        ]

    # Instructions
    steps = raw.get("steps") or raw.get("instructions") or raw.get("recipe_steps") or ""
    if isinstance(steps, list):
        parts = []
        for i, step in enumerate(steps, 1):
            if isinstance(step, str):
                parts.append(f"{i}. {_strip_html(step)}")
            elif isinstance(step, dict):
                h = _strip_html(step.get("headline") or "")
                d = _strip_html(step.get("description") or step.get("text") or "")
                parts.append(f"{i}. " + (f"{h}: {d}" if h and d else h or d))
        instructions = "\n".join(parts)
    else:
        instructions = _strip_html(str(steps))

    # Category
    cat = raw.get("category") or raw.get("categories") or "Miscellaneous"
    if isinstance(cat, dict):
        data = cat.get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        cat = (data.get("attributes") or {}).get("category_name") or \
              (data.get("attributes") or {}).get("name") or "Miscellaneous"
    elif isinstance(cat, list):
        cat = cat[0] if cat else "Miscellaneous"

    # Image
    img = ""
    img_raw = raw.get("images") or raw.get("image")
    if isinstance(img_raw, dict):
        data = img_raw.get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        path = (data.get("attributes") or {}).get("url", "")
        img = (TJ_BASE + path) if path.startswith("/") else path
    elif isinstance(img_raw, str):
        img = (TJ_BASE + img_raw) if img_raw.startswith("/") else img_raw

    tags_raw = raw.get("tags") or []
    tags = (
        ", ".join((t.get("attributes") or {}).get("tag_name", "") for t in tags_raw.get("data", []) if isinstance(t, dict))
        if isinstance(tags_raw, dict)
        else ", ".join(str(t) for t in tags_raw) if isinstance(tags_raw, list)
        else str(tags_raw)
    )

    return {
        "title": title,
        "ingredients_raw": ing_raw if isinstance(ing_raw, list) else [],
        "instructions": instructions,
        "image": img,
        "category": cat,
        "cuisine": "American",
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

class _LiExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._items: list[str] = []
        self._buf: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self._depth += 1
            if self._depth == 1:
                self._buf = []

    def handle_endtag(self, tag):
        if tag == "li" and self._depth == 1:
            t = "".join(self._buf).strip()
            if t:
                self._items.append(t)
        if tag == "li":
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._depth >= 1:
            self._buf.append(data)


def _li_items(html: str) -> list[str]:
    p = _LiExtractor()
    p.feed(html)
    return p._items


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


# ---------------------------------------------------------------------------
# Scrape a single recipe page
# ---------------------------------------------------------------------------

def scrape_recipe(url: str) -> dict | None:
    html = fetch(url)
    if not html:
        return None

    data = _scrape_via_recipe_scrapers(url, html) or _scrape_via_next_data(html)

    if not data or not data.get("title") or not data.get("instructions"):
        logger.warning(f"  could not extract recipe data from {url}")
        return None

    ingredients = normalise_ingredients(data.get("ingredients_raw") or [])
    slug = url.rstrip("/").split("/")[-1] or re.sub(r"[^a-z0-9]+", "-", data["title"].lower())
    tags = data.get("tags", "")
    if isinstance(tags, list):
        tags = ", ".join(str(t) for t in tags)

    return {
        "title": data["title"],
        "category": data.get("category") or "Miscellaneous",
        "area": data.get("cuisine") or "American",
        "tags": tags,
        "ingredients": ingredients,
        "instructions": data["instructions"],
        "image": data.get("image") or "",
        "slug": slug,
    }


# ---------------------------------------------------------------------------
# Ingest to Pinecone
# ---------------------------------------------------------------------------

def ingest_recipe(index, recipe: dict) -> bool:
    source_id = f"traderjoes_{recipe['slug']}"
    recipe_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_id))  # deterministic → idempotent

    try:
        existing = index.fetch(ids=[recipe_id])
        if existing.get("vectors") and recipe_id in existing["vectors"]:
            logger.info(f"  skip (exists): {recipe['title']}")
            return False
    except Exception:
        pass

    ingredients_str = ", ".join(f"{i['qty']} {i['item']}".strip() for i in recipe["ingredients"])
    document = (
        f"RECIPE TITLE: {recipe['title']}\n"
        f"CATEGORY: {recipe['category']}\n"
        f"AREA: {recipe['area']}\n"
        f"TAGS: {recipe['tags']}\n"
        f"INGREDIENTS: {ingredients_str}\n"
        f"INSTRUCTIONS: {recipe['instructions']}"
    )

    logger.info(f"  estimating nutrition: {recipe['title']}")
    nutrition = estimate_nutrition(recipe["title"], recipe["ingredients"])

    metadata = {
        "title": recipe["title"],
        "category": recipe["category"],
        "area": recipe["area"],
        "tags": recipe["tags"],
        "ingredients": json.dumps(recipe["ingredients"]),
        "instructions": recipe["instructions"],
        "source": source_id,
        "image": recipe["image"],
        "nutrition": json.dumps(nutrition),
    }

    embedding = get_embedding(document)
    index.upsert(vectors=[{"id": recipe_id, "values": embedding, "metadata": metadata}])
    logger.info(f"  ingested: {recipe['title']} ({recipe['category']})")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def ingest_all(max_recipes: int = None, delay: float = 1.5):
    if cf is None:
        logger.error("Aborting: curl_cffi is required.  pip install curl_cffi")
        return

    index = get_or_create_index()
    recipe_urls = get_recipe_urls()

    if not recipe_urls:
        return

    if max_recipes:
        recipe_urls = recipe_urls[:max_recipes]

    ingested = skipped = errors = 0
    for i, url in enumerate(recipe_urls, 1):
        logger.info(f"[{i}/{len(recipe_urls)}] {url}")
        try:
            recipe = scrape_recipe(url)
            if recipe:
                added = ingest_recipe(index, recipe)
                ingested += 1 if added else 0
                skipped += 0 if added else 1
            else:
                errors += 1
        except Exception as e:
            logger.error(f"  unexpected error: {e}")
            errors += 1
        time.sleep(delay)

    logger.info(f"Done — ingested: {ingested}, skipped: {skipped}, errors: {errors}")
    try:
        logger.info(f"Index stats: {index.describe_index_stats()}")
    except Exception:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Trader Joe's recipes into Pinecone")
    parser.add_argument("--max-recipes", type=int, default=None, help="Cap total recipes (default: all)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests (default: 1.5)")
    args = parser.parse_args()

    ingest_all(max_recipes=args.max_recipes, delay=args.delay)
