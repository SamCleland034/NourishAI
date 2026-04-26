
import chromadb
import json
import logging
import httpx
import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair_images")

# --- Cloud Service Config ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection(name="recipes")

async def upload_to_supabase(http_client, rid, url, retries=2):
    """Downloads image and uploads to Supabase Storage, returns public URL."""
    if not url or not supabase: return None
    if "supabase.co" in url: return url # Already in Supabase
    
    ext = url.split('.')[-1].split('?')[0] if '.' in url else 'jpg'
    if len(ext) > 4: ext = 'jpg'
    filename = f"{rid}.{ext}"
    supabase_public_url = f"{SUPABASE_URL}/storage/v1/object/public/recipe-images/{filename}"

    # Check if already exists in Supabase
    try:
        check_resp = await http_client.head(supabase_public_url)
        if check_resp.status_code == 200:
            return supabase_public_url
    except: pass

    for attempt in range(retries + 1):
        try:
            logger.info(f"Downloading for Supabase: {url} (Attempt {attempt+1})")
            resp = await http_client.get(url, follow_redirects=True, timeout=10.0)
            if resp.status_code == 200:
                # Upload to Supabase
                supabase.storage.from_("recipe-images").upload(
                    path=filename,
                    file=resp.content,
                    file_options={"content-type": f"image/{ext}"}
                )
                return supabase_public_url
            break 
        except Exception as e:
            if "already exists" in str(e).lower():
                return supabase_public_url
            if attempt == retries:
                logger.error(f"Failed to upload {url} after {retries+1} attempts: {e}")
            else:
                await asyncio.sleep(1) 
    
    return None

async def repair():
    results = collection.get(include=["metadatas"])
    ids = results['ids']
    metadatas = results['metadatas']
    
    # trust_env=True helps with proxy issues
    async with httpx.AsyncClient(trust_env=True) as http_client:
        for i, meta in enumerate(metadatas):
            rid = ids[i]
            title = meta.get("title")
            image = meta.get("image")
            source = meta.get("source", "")
            
            # 1. Check if image is missing or a placeholder
            if not image or "placehold" in image or "via.placeholder" in image:
                logger.info(f"Repairing image for: {title}")
                
                new_image = None
                if "themealdb_" in source:
                    meal_id = source.replace("themealdb_", "")
                    try:
                        resp = await http_client.get(f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}")
                        data = resp.json()
                        if data.get("meals"):
                            new_image = data["meals"][0].get("strMealThumb")
                            logger.info(f"  -> Found MealDB image: {new_image}")
                    except Exception as e:
                        logger.error(f"  -> Failed MealDB lookup: {e}")

                if not new_image:
                    new_image = f"https://placehold.co/600x400?text={title.replace(' ', '+')}"
                
                image = new_image
            
            # 2. Upload to Supabase
            supabase_url = await upload_to_supabase(http_client, rid, image)
            
            if supabase_url and supabase_url != meta.get("image"):
                meta["image"] = supabase_url
                collection.update(ids=[rid], metadatas=[meta])
                logger.info(f"Updated {title} with Supabase URL")

    logger.info(f"Successfully processed all recipes.")

if __name__ == "__main__":
    asyncio.run(repair())
