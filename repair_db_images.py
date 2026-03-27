
import chromadb
import json
import logging
import httpx
import asyncio
import os
from chromadb.utils import embedding_functions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair_images")

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection(name="recipes")

IMAGES_DIR = os.path.join("static", "recipe_images")
os.makedirs(IMAGES_DIR, exist_ok=True)

async def download_image(http_client, rid, url, retries=2):
    """Downloads image if not exists and returns local filename with retries."""
    if not url: return None
    
    ext = url.split('.')[-1] if '.' in url else 'jpg'
    if len(ext) > 4: ext = 'jpg'
    filename = f"{rid}.{ext}"
    local_path = os.path.join(IMAGES_DIR, filename)

    if os.path.exists(local_path):
        return filename

    for attempt in range(retries + 1):
        try:
            logger.info(f"Downloading image locally: {url} (Attempt {attempt+1})")
            resp = await http_client.get(url, follow_redirects=True, timeout=10.0)
            if resp.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                return filename
            break # Stop if we got a 404 or other non-retryable error
        except Exception as e:
            if attempt == retries:
                logger.error(f"Failed to download {url} after {retries+1} attempts: {e}")
            else:
                await asyncio.sleep(1) # Wait before retry
    
    return None

async def repair():
    results = collection.get(include=["metadatas"])
    ids = results['ids']
    metadatas = results['metadatas']
    
    updated_metadatas = []
    updated_ids = []
    
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
                
                # A. If it's a TheMealDB recipe, try to fetch the real thumb
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

                # B. If still no image, use working placeholder
                if not new_image:
                    new_image = f"https://placehold.co/600x400?text={title.replace(' ', '+')}"
                
                image = new_image
            
            # 2. Always try to ensure it's downloaded locally
            await download_image(http_client, rid, image)
            
            # We don't update the DB metadata to point to local paths yet
            # because the backend handles the mapping dynamically in repair_recipe.
            # However, we'll ensure the 'image' field in DB is a valid URL.
            meta["image"] = image
            updated_metadatas.append(meta)
            updated_ids.append(rid)

    if updated_ids:
        collection.update(ids=updated_ids, metadatas=updated_metadatas)
        logger.info(f"Successfully processed {len(updated_ids)} recipes.")

if __name__ == "__main__":
    asyncio.run(repair())
