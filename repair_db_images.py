
import chromadb
import json
import logging
import httpx
import asyncio
from chromadb.utils import embedding_functions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair_images")

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection(name="recipes")

async def repair():
    results = collection.get(include=["metadatas"])
    ids = results['ids']
    metadatas = results['metadatas']
    
    updated_metadatas = []
    updated_ids = []
    
    async with httpx.AsyncClient() as http_client:
        for i, meta in enumerate(metadatas):
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

                # B. If still no image, we would ideally search, but for now let's ensure it's at least not broken
                if not new_image:
                    # We'll use a specific placeholder that's definitely working
                    new_image = f"https://placehold.co/600x400?text={title.replace(' ', '+')}"
                
                meta["image"] = new_image
                updated_metadatas.append(meta)
                updated_ids.append(ids[i])
            else:
                # Ensure all required fields are in metadata even if image is fine
                meta["image"] = image
                updated_metadatas.append(meta)
                updated_ids.append(ids[i])

    if updated_ids:
        # ChromaDB update requires list of IDs and list of Metadatas
        collection.update(ids=updated_ids, metadatas=updated_metadatas)
        logger.info(f"Successfully updated {len(updated_ids)} recipes.")

if __name__ == "__main__":
    asyncio.run(repair())
