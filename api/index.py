import os
import uuid
import time
import json
import logging
import hashlib
import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from recipe_scrapers import scrape_me
import httpx
import shutil

from pinecone import Pinecone, ServerlessSpec
from supabase import create_client, Client
import litellm
from openai import OpenAI
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# --- STATIC CONFIG ---
# On Vercel, we must use /tmp for any write operations
IS_VERCEL = os.getenv("VERCEL") == "1"
DATA_DIR = "/tmp" if IS_VERCEL else os.getenv("DATA_DIR", ".")
STATIC_DIR = os.path.join(DATA_DIR, "static")
IMAGES_DIR = os.path.join(STATIC_DIR, "recipe_images")

try:
    os.makedirs(IMAGES_DIR, exist_ok=True)
except Exception as e:
    logging.warning(f"Could not create IMAGES_DIR: {e}")

# Disable LiteLLM caching which can cause read-only filesystem errors
litellm.cache = None

# Google API Imports
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Allow insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# --- MODELS CONFIG ---
DEFAULT_MODEL = "gemini/gemini-2.0-flash"

DAY_MAP = {
    "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu", "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
    "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"
}
MEAL_MAP = {
    "breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner",
    "brkfst": "Breakfast", "lch": "Lunch", "din": "Dinner"
}

def normalize_plan(plan, recs):
    valid_ids = {r["id"] for r in recs}
    name_to_id = {r["name"].lower(): r["id"] for r in recs}
    final_plan = {d: {} for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

    def normalize_meals(m_dict):
        new_meals = {}
        if not isinstance(m_dict, dict): return {}
        for k, v in m_dict.items():
            target_meal = MEAL_MAP.get(str(k).strip().lower(), k)
            if v and v not in valid_ids:
                v = name_to_id.get(str(v).strip().lower(), v)
            new_meals[target_meal] = v
        return new_meals

    if isinstance(plan, dict):
        for day, meals in plan.items():
            target_day = DAY_MAP.get(str(day).strip().lower())
            if target_day: final_plan[target_day] = normalize_meals(meals)
    elif isinstance(plan, list):
        for item in plan:
            if isinstance(item, dict):
                day_key = item.get("day") or item.get("date")
                meals = item.get("meals") or {k:v for k,v in item.items() if k != "day" and k != "date"}
                if day_key:
                    target_day = DAY_MAP.get(str(day_key).strip().lower())
                    if target_day: final_plan[target_day] = normalize_meals(meals)
    return final_plan

# --- Google OAuth Config ---
def find_client_secret():
    # Look in current dir and parent dir (root)
    dirs_to_check = [".", ".."]
    for d in dirs_to_check:
        try:
            for f in os.listdir(d):
                if f.startswith("client_secret") and f.endswith(".json"):
                    return os.path.join(d, f)
        except: continue
    return "client_secret.json"

CLIENT_SECRET_FILE = find_client_secret()
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")

# --- Cloud Service Config ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "recipes")

# OpenAI config for embeddings (1536 dims)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
oa_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
EMBEDDING_MODEL = "text-embedding-3-small"

# LiteLLM looks for GEMINI_API_KEY; user has GOOGLE_API_KEY in .env
if not os.getenv("GEMINI_API_KEY") and os.getenv("GOOGLE_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_KEY missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None
pc = Pinecone(api_key=PINECONE_API_KEY) if PINECONE_API_KEY else None

# --- DB Helper (Legacy compatibility wrapped around Supabase) ---
def init_db():
    # In Supabase, tables are usually created via dashboard or migrations.
    # We'll assume they exist for now or provide a SQL snippet in documentation.
    logger.info("Supabase client initialized.")

init_db()

def ensure_supabase_image(rid, url, retries=2):
    """Downloads external images and uploads to Supabase Storage to ensure persistence."""
    if not url or "placehold.co" in url or "via.placeholder" in url:
        return url
    if not supabase:
        return url

    # Check if image already exists in Supabase to avoid re-uploading
    ext = url.split('.')[-1].split('?')[0]
    if len(ext) > 4: ext = "jpg"
    filename = f"{rid}.{ext}"
    
    supabase_public_url = f"{SUPABASE_URL}/storage/v1/object/public/recipe-images/{filename}"
    
    try:
        # Quick check if it exists (using head request or similar)
        # For simplicity, we can also just try to upload and handle 'already exists' or just overwrite.
        # But let's check first to save bandwidth.
        with httpx.Client() as client:
            check_resp = client.head(supabase_public_url)
            if check_resp.status_code == 200:
                return supabase_public_url

        logger.info(f"Uploading image for {rid} to Supabase: {url}")
        with httpx.Client(follow_redirects=True, timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                # Upload to Supabase 'recipe-images' bucket
                supabase.storage.from_("recipe-images").upload(
                    path=filename,
                    file=resp.content,
                    file_options={"content-type": f"image/{ext}"}
                )
                return supabase_public_url
    except Exception as e:
        # If it fails because it already exists, that's fine
        if "already exists" in str(e).lower():
            return supabase_public_url
        logger.error(f"Failed to cache image to Supabase {url}: {e}")
    
    return url

def estimate_multiple_nutrition(recipes_list):
    """Estimate Calories, Protein, Carbs, Fat for multiple recipes in ONE LLM call."""
    if not recipes_list: return {}
    
    input_data = []
    for r in recipes_list:
        input_data.append({"id": r["id"], "title": r.get("name"), "ingredients": r.get("ingredients")})

    prompt = (
        "Estimate average Calories, Protein(g), Carbs(g), and Fat(g) for the following recipes based on their titles and ingredients. "
        "Return a JSON object where the keys are the recipe IDs and the values are objects with keys: calories, protein, carbs, fat. "
        "Ensure all values are numbers (not strings). Return ONLY the raw JSON object.\n\n"
        f"Recipes: {json.dumps(input_data)}"
    )

    try:
        logger.info(f"Estimating nutrition for {len(recipes_list)} recipes...")
        response = litellm.completion(
            model=DEFAULT_MODEL,
            messages=[{"role": "system", "content": "You are a professional dietitian JSON API."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        raw_content = response.choices[0].message.content
        # Clean potential markdown
        if "```json" in raw_content:
            raw_content = raw_content.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_content:
            raw_content = raw_content.split("```")[1].strip()
            
        print(f"DEBUG: Raw Nutrition Response Content: {raw_content[:200]}...")
        res = json.loads(raw_content) or {}
        logger.info(f"Received nutrition results for {len(res)} recipes.")
        return res
    except Exception as e:
        logger.error(f"Aggregated nutrition error: {e}")
        print(f"DEBUG: Detailed AI Error: {type(e).__name__}: {str(e)}")
        # Return fallback for each recipe to avoid 0s
        fallback_results = {}
        for r in recipes_list:
            # Simple heuristic based on category or default
            fallback_results[r["id"]] = {"calories": 500, "protein": 25, "carbs": 60, "fat": 20}
        return fallback_results

def repair_recipe(rid, meta):
    """Helper to ensure all required fields are present in a recipe object."""
    img = meta.get("image")
    title = meta.get("title", "Recipe")
    
    # Nutritional data from metadata or estimate
    nutri_str = meta.get("nutrition")
    if nutri_str:
        try: 
            if isinstance(nutri_str, str):
                nutrition = json.loads(nutri_str)
            else:
                nutrition = nutri_str
        except: nutrition = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    else:
        nutrition = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

    # 1. Handle images: prioritize supabase/external
    if not img or "via.placeholder" in img or "placehold.co" in img:
        img = f"https://placehold.co/600x400?text={title.replace(' ', '+')}"
    elif img.startswith("/static/recipe_images/"):
        # Local paths don't work on Vercel, we should ideally migrate these
        # For now, if we see a local path, let's keep it but ideally we'd re-download to Supabase
        pass
    elif not img.startswith("http"):
        # Might be just a filename, assume it's in Supabase if not starting with /static
        img = f"{SUPABASE_URL}/storage/v1/object/public/recipe-images/{img}"
    else:
        # It's an external URL, try to cache it in Supabase
        img = ensure_supabase_image(rid, img)
    
    return {
        "id": rid,
        "name": title,
        "category": meta.get("category"),
        "cuisine": meta.get("area"),
        "ingredients": json.loads(meta.get("ingredients", "[]")) if isinstance(meta.get("ingredients"), str) else meta.get("ingredients", []),
        "instructions": meta.get("instructions"),
        "image": img,
        "nutrition": nutrition
    }

def calculate_schedule_stats(schedule, recipe_map):
    """Aggregates nutritional stats for a schedule, estimating missing values in one batch."""
    daily_stats = {d: {"calories": 0, "protein": 0, "carbs": 0, "fat": 0} for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
    weekly_stats = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    
    # Aggregated estimate - REMOVED AS PER USER REQUEST to simplify and avoid problems.
    # We will now just rely on existing data and not try to call LLMs for missing values.
    # We'll skip the 'to_estimate' logic and just sum what we HAVE.
    
    # We don't need the to_estimate loop or the estimation call anymore.
    # Just ensure we have a fallback for sum totals.

    # Sum totals
    if not isinstance(schedule, dict):
        logger.warning(f"Stats received non-dict schedule: {type(schedule)}")
        return daily_stats, weekly_stats
        
    for day, meals in schedule.items():
        if day not in daily_stats: continue
        if isinstance(meals, dict):
            for m, rid in meals.items():
                if rid and rid in recipe_map:
                    nut = recipe_map[rid].get("nutrition")
                    if not isinstance(nut, dict):
                        nut = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
                    
                    # Final sanity check: if it's still missing or effectively 0, sum nothing but don't crash
                    for k in weekly_stats.keys():
                        try:
                            # Handle potential string values from database
                            val = float(nut.get(k, 0))
                        except (ValueError, TypeError):
                            val = 0
                        daily_stats[day][k] += val
                        weekly_stats[k] += val
                        
    logger.info(f"Schedule stats calculated: Total {weekly_stats['calories']} kcal")
    return daily_stats, weekly_stats

app = FastAPI(title="NourishAI Backend")
app.mount("/static", StaticFiles(directory="static"), name="static")

# SESSION MIDDLEWARE
app.add_middleware(SessionMiddleware, secret_key="nourish-ai-secret-key-change-this")

# FIXED CORS: Specified origins are required when allow_credentials=True
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "v1.1-persistence-fix", "timestamp": time.time()}

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Initialize Pinecone Index
def get_pinecone_index():
    if not pc: return None
    try:
        return pc.Index(PINECONE_INDEX_NAME)
    except:
        logger.error(f"Index {PINECONE_INDEX_NAME} not found!")
        return None

index = get_pinecone_index()

# Helper for text embeddings (same as default ChromaDB)
def get_embedding(text):
    # Use OpenAI text-embedding-3-small (1536 dims)
    if not oa_client:
        logger.error("No OpenAI client found to generate embedding. Check OPENAI_API_KEY in Vercel environment.")
        return [0.0] * 1536
    
    try:
        res = oa_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
        emb = res.data[0].embedding
        logger.info(f"Generated embedding for query: '{text[:20]}...' (dims: {len(emb)})")
        return emb
    except Exception as e:
        logger.error(f"Embedding error (OpenAI): {e}")
        return [0.0] * 1536

# --- MODELS ---
class AuthRequest(BaseModel):
    username: str
    password: str

class UserOnlyRequest(BaseModel):
    user_id: int
    week_id: Optional[str] = "recurring"

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = []
    num_recipes: int = 3
    exclude_ids: List[str] = []
    user_id: Optional[int] = None
    week_id: Optional[str] = None
    current_schedule: Optional[Dict[str, Any]] = None

class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 20

class GroceryRequest(BaseModel):
    user_id: int
    week_id: str
    schedule: Optional[Dict[str, Any]] = None
    unit_system: Optional[str] = "imperial"

class FavoriteRequest(BaseModel):
    user_id: int
    recipe: Dict[str, Any]

class ScheduleRequest(BaseModel):
    user_id: int
    week_id: str
    schedule: Dict[str, Any]

# --- GOOGLE CALENDAR ---
@app.get("/api/auth/google/login/{user_id}")
async def google_login(user_id: int, request: Request):
    if not os.path.exists(CLIENT_SECRET_FILE):
        raise HTTPException(status_code=500, detail="Secret file missing.")
    flow = Flow.from_client_secrets_file(CLIENT_SECRET_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    request.session['oauth_state'] = state
    request.session['oauth_user_id'] = user_id
    request.session['code_verifier'] = flow.code_verifier
    return {"url": auth_url}

@app.get("/api/auth/google/callback")
async def google_callback(request: Request):
    try:
        state = request.session.get('oauth_state')
        user_id = request.session.get('oauth_user_id')
        code_verifier = request.session.get('code_verifier')
        if not state or not user_id: return HTMLResponse("<h1>Session Expired</h1>")
        flow = Flow.from_client_secrets_file(CLIENT_SECRET_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI, state=state)
        flow.code_verifier = code_verifier
        flow.fetch_token(authorization_response=str(request.url))
        
        supabase.table("google_tokens").upsert({"user_id": user_id, "token_json": flow.credentials.to_json()}).execute()
        return HTMLResponse("<h1>Success!</h1><script>setTimeout(()=>window.close(), 1500);</script>")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>")

@app.get("/api/google/status/{user_id}")
def get_google_status(user_id: int):
    try:
        res = supabase.table("google_tokens").select("user_id").eq("user_id", user_id).execute()
        return {"connected": len(res.data) > 0}
    except Exception as e:
        logger.error(f"Google status error: {e}")
        return {"connected": False}

@app.post("/api/google/export")
def export_to_calendar(req: ScheduleRequest):
    try:
        res = supabase.table("google_tokens").select("token_json").eq("user_id", req.user_id).execute()
        if not res.data: raise HTTPException(status_code=401, detail="Not connected")
        row = res.data
        
        creds = Credentials.from_authorized_user_info(json.loads(row[0]["token_json"]), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            supabase.table("google_tokens").upsert({"user_id": req.user_id, "token_json": creds.to_json()}).execute()

        service = build('calendar', 'v3', credentials=creds)
        year, week = map(int, req.week_id.split("-W"))
        # Robust Sunday calculation
        start_date = datetime.datetime.strptime(f'{year}-W{week}-0', "%Y-W%W-%w").date()
        
        day_offsets = {"Sun": 0, "Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6}
        meal_times = {"Breakfast": "08:00:00", "Lunch": "12:00:00", "Dinner": "19:00:00"}

        res_favs = supabase.table("favorites").select("recipe_id, recipe_data").eq("user_id", req.user_id).execute()
        fav_map = {r["recipe_id"]: r["recipe_data"] for r in res_favs.data} if res_favs.data else {}

        events_created = 0
        for day, meals in req.schedule.items():
            if day not in day_offsets: continue
            curr = start_date + datetime.timedelta(days=day_offsets[day])
            for m_type, rid in meals.items():
                if not rid: continue
                rec = fav_map.get(rid)
                recipe_name = rec['name'] if rec else "Meal"
                
                # Robust ingredient string creation
                ingredients = []
                if rec and "ingredients" in rec:
                    for ing in rec["ingredients"]:
                        if isinstance(ing, dict): ingredients.append(f"{ing.get('qty', '')} {ing.get('item', '')}")
                        else: ingredients.append(str(ing))
                
                start = f"{curr}T{meal_times[m_type]}Z"
                end = (datetime.datetime.combine(curr, datetime.time.fromisoformat(meal_times[m_type])) + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                
                event = {
                    'summary': f'🍴 {m_type}: {recipe_name}',
                    'description': f'NourishAI Plan\n\nIngredients:\n' + "\n".join(ingredients),
                    'start': {'dateTime': start, 'timeZone': 'UTC'},
                    'end': {'dateTime': end, 'timeZone': 'UTC'}
                }
                service.events().insert(calendarId='primary', body=event).execute()
                events_created += 1
        return {"status": "success", "events_created": events_created}
    except Exception as e:
        logger.error(f"Export crash: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/auth/signup")
def signup(req: AuthRequest):
    try:
        res = supabase.table("users").insert({"username": req.username, "password_hash": hash_password(req.password)}).execute()
        if res.data:
            return {"user_id": res.data[0]["id"], "username": req.username}
        raise HTTPException(status_code=400, detail="Signup failed")
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=400, detail=f"Signup failed: {str(e)}")

@app.post("/api/auth/login")
def login(req: AuthRequest):
    res = supabase.table("users").select("id, username").eq("username", req.username).eq("password_hash", hash_password(req.password)).execute()
    if res.data:
        return {"user_id": res.data[0]["id"], "username": res.data[0]["username"]}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/favorites")
def add_favorite(req: FavoriteRequest):
    # Map 'recipe' to 'recipe_data' for Supabase
    rid = req.recipe.get("id")
    data = {"user_id": req.user_id, "recipe_id": rid, "recipe_data": req.recipe}
    supabase.table("favorites").upsert(data, on_conflict="user_id, recipe_id").execute()
    return {"status": "ok"}

@app.post("/api/favorites/remove")
def remove_favorite(req: FavoriteRequest):
    rid = req.recipe.get("id")
    supabase.table("favorites").delete().eq("user_id", req.user_id).eq("recipe_id", rid).execute()
    return {"status": "ok"}

@app.get("/api/favorites/{user_id}")
def get_favorites(user_id: int):
    try:
        res = supabase.table("favorites").select("recipe_data").eq("user_id", user_id).execute()
        recipes = [r["recipe_data"] for r in res.data] if res.data else []
    except Exception as e:
        logger.error(f"Favorites fetch error: {e}")
        recipes = []
    
    repaired = []
    for r in recipes:
        # Check if we need better image/metadata from Pinecone
        if not r.get("image") or "via.placeholder" in r.get("image", ""):
            if index:
                try:
                    fetch_res = index.fetch(ids=[r.get("id")])
                    if fetch_res.get('vectors') and r.get("id") in fetch_res['vectors']:
                        meta = fetch_res['vectors'][r.get("id")]['metadata']
                        repaired.append(repair_recipe(r.get("id"), meta))
                        continue
                except: pass
        repaired.append(r)
    return {"recipes": repaired}

@app.post("/api/schedule")
def save_schedule(req: ScheduleRequest):
    data = {"user_id": req.user_id, "week_id": req.week_id, "schedule_json": req.schedule}
    supabase.table("schedules").upsert(data, on_conflict="user_id, week_id").execute()
    return {"status": "ok"}

@app.get("/api/schedule/{user_id}/{week_id}")
def get_schedule(user_id: int, week_id: str):
    # Try specific week first
    res = supabase.table("schedules").select("schedule_json").eq("user_id", user_id).eq("week_id", week_id).execute()
    
    # Fallback to recurring if not found
    is_recurring_applied = False
    if not res.data:
        res = supabase.table("schedules").select("schedule_json").eq("user_id", user_id).eq("week_id", "recurring").execute()
        if res.data: is_recurring_applied = True
    
    schedule = res.data[0]["schedule_json"] if res.data else {}
    
    recipe_ids = set()
    for day in schedule.values():
        if isinstance(day, dict):
            for rid in day.values():
                if rid: recipe_ids.add(rid)
    
    recipe_map = {}
    idx_obj = get_pinecone_index()
    if recipe_ids and idx_obj:
        try:
            fetch_res = idx_obj.fetch(ids=list(recipe_ids))
            if fetch_res.get('vectors'):
                for rid, vector_data in fetch_res['vectors'].items():
                    recipe_map[rid] = repair_recipe(rid, vector_data['metadata'])
        except Exception as e:
            logger.error(f"Pinecone schedule fetch error: {e}")
            
    daily_stats, weekly_stats = calculate_schedule_stats(schedule, recipe_map)

    return {
        "schedule": schedule, 
        "recipes": list(recipe_map.values()), 
        "is_recurring_applied": is_recurring_applied,
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats
    }

class UserOnlyRequest(BaseModel):
    user_id: int

@app.post("/api/planner/autofill")
def autofill_planner(req: UserOnlyRequest):
    # Logic: Get favorites to find preferences, then query DB for 21 diverse recipes
    res_favs = supabase.table("favorites").select("recipe_data").eq("user_id", req.user_id).execute()
    favs = [r["recipe_data"] for r in res_favs.data] if res_favs.data else []
    
    # Build a query from favorites
    q = " ".join({r.get("category","")+" "+r.get("cuisine","") for r in favs}).strip() or "healthy delicious recipes"
    
    # Get a large pool from Pinecone
    pool = []
    idx_obj = get_pinecone_index()
    if idx_obj:
        emb = get_embedding(q)
        res = idx_obj.query(vector=emb, top_k=40, include_metadata=True)
        if res.get('matches'):
            for m in res['matches']:
                pool.append(repair_recipe(m['id'], m['metadata']))
    
    import random
    if not pool:
        # Emergency backup - limited by Pinecone lack of 'peek'
        # We'll just use a generic query
        emb = get_embedding("popular healthy recipes")
        if idx_obj:
            res = idx_obj.query(vector=emb, top_k=21, include_metadata=True)
            pool = [repair_recipe(m['id'], m['metadata']) for m in res.get('matches', [])]
    
    if not pool:
        logger.warning("Planner pool is still empty after emergency query. Returning empty.")
        return {"schedule": {}, "recipes": {}, "daily_stats": {}, "weekly_stats": {}}

    random.shuffle(pool)
    new_schedule = {}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    meals = ["Breakfast", "Lunch", "Dinner"]
    
    idx = 0
    for d in days:
        new_schedule[d] = {}
        for m in meals:
            picked = pool[idx % len(pool)]
            if m == "Breakfast":
                for search_idx in range(idx, idx + 5):
                    candidate = pool[search_idx % len(pool)]
                    if candidate.get("category") == "Breakfast":
                        picked = candidate
                        break
            new_schedule[d][m] = picked.get("id")
            idx += 1
            
    recipe_map = {r["id"]: r for r in pool}
    recipes_list = list(recipe_map.values())
    daily_stats, weekly_stats = calculate_schedule_stats(new_schedule, recipe_map)

    # PERSISTENCE: Save to DB so it doesn't disappear on refresh
    try:
        if req.user_id and req.week_id:
            logger.info(f"Saving generated plan for user {req.user_id} week {req.week_id}")
            supabase.table("schedules").upsert({
                "user_id": req.user_id,
                "week_id": req.week_id,
                "schedule_json": new_schedule
            }, on_conflict="user_id, week_id").execute()
    except Exception as e:
        logger.error(f"Failed to auto-save plan: {e}")

    return {
        "schedule": new_schedule, 
        "recipes": recipes_list,
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats
    }

@app.post("/api/planner/prompt")
def planner_prompt(req: ChatRequest):
    # Similar to chat but specialized for arrangement
    recs = []
    ctx = ""
    idx_obj = get_pinecone_index()
    if idx_obj:
        emb = get_embedding(req.message)
        res = idx_obj.query(vector=emb, top_k=50, include_metadata=True)
        if res.get('matches'):
            for m in res['matches']:
                obj = repair_recipe(m['id'], m['metadata'])
                recs.append(obj); ctx += f"ID: {obj['id']} | {obj['name']} ({obj['category']})\n"
                if len(recs) >= 20: break
    
    if not recs and idx_obj:
        logger.info("Planner prompt primary search empty. Trying fallback.")
        emb = get_embedding("popular healthy recipes")
        res = idx_obj.query(vector=emb, top_k=20, include_metadata=True)
        if res.get('matches'):
            for m in res['matches']:
                obj = repair_recipe(m['id'], m['metadata'])
                recs.append(obj); ctx += f"ID: {obj['id']} | {obj['name']} ({obj['category']})\n"

    current_sched_str = json.dumps(req.current_schedule) if req.current_schedule else "None"

    sys = (
        "You are a meal planner assistant. Arrange or MODIFY a 7-day schedule (Mon-Sun, Breakfast/Lunch/Dinner) based on the user request. "
        "Use ONLY the recipe IDs provided below for the JSON values. "
        "IMPORTANT: The user has an EXISTING schedule provided below. "
        "If the user asks to change a specific day or meal, ONLY change those and KEEP all other existing recipe IDs exactly as they are. "
        "If the user asks for a new plan, you can replace more items. "
        "IMPORTANT: Use exactly these short keys for days: Mon, Tue, Wed, Thu, Fri, Sat, Sun. "
        "IMPORTANT: Use exactly these meal keys: Breakfast, Lunch, Dinner. "
        "IMPORTANT: Return a valid JSON within <PLAN> tags representing the FULL 7-day schedule (existing + changes). "
        "IMPORTANT: The JSON values must be the Recipe IDs (UUIDs), NOT the names. "
        "IMPORTANT: Never show the Recipe IDs (UUIDs) in your natural language explanation. Only use them inside the <PLAN> tags.\n\n"
        f"EXISTING SCHEDULE: {current_sched_str}\n\n"
        f"AVAILABLE NEW RECIPES:\n{ctx}"
    )
    logger.info(f"PLANNER PROMPT SEARCH RESULT SIZE: {len(recs)}")
    try:
        response = litellm.completion(model=DEFAULT_MODEL, messages=[{"role":"system","content":sys}, {"role":"user","content":req.message}])
        msg = response.choices[0].message.content
        logger.info(f"PLANNER PROMPT AI RESPONSE RAW: {msg[:500]}...")
    except Exception as e:
        logger.error(f"LLM Error in Planner: {e}")
        if "429" in str(e) or "limit" in str(e).lower():
            raise HTTPException(status_code=429, detail="AI Rate Limit Reached. Please wait a minute and try again.")
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")
    
    plan = None
    
    if "<PLAN>" in msg:
        try:
            # Strip potential markdown backticks around the plan
            plan_str = msg.split("<PLAN>")[1].split("</PLAN>")[0].strip()
            if plan_str.startswith("```json"): plan_str = plan_str[7:]
            if plan_str.startswith("```"): plan_str = plan_str[3:]
            if plan_str.endswith("```"): plan_str = plan_str[:-3]
            plan = json.loads(plan_str.strip())
            msg = msg.split("<PLAN>")[0].strip()
            # Remove trailing backticks from the msg
            if msg.endswith("```json"): msg = msg[:-7].strip()
            if msg.endswith("```"): msg = msg[:-3].strip()
        except Exception as e:
            logger.error(f"Plan Parsing Error: {e}")
            raise HTTPException(status_code=500, detail=f"Parsing Error: {str(e)}\n\nAI Response: {msg[:200]}...")
        
        # Use centralized normalization
        plan = normalize_plan(plan, recs)
        
        # MERGE LOGIC: Ensure that if the AI returned a partial or messed up plan, we respect the original
        if req.current_schedule:
            merged_plan = json.loads(json.dumps(req.current_schedule)) # Deep copy
            for day, meals in plan.items():
                if day in merged_plan:
                    for meal, rid in meals.items():
                        if rid: # Only overwrite if AI actually provided a new ID
                            merged_plan[day][meal] = rid
                else:
                    merged_plan[day] = meals
            plan = merged_plan

        logger.info(f"PLANNER FINAL KEYS: {list(plan.keys())}")
        
    # Calculate stats if plan generated
    daily_stats = None
    weekly_stats = None
    if plan:
        recipe_map = {r["id"]: r for r in recs}
        try:
            daily_stats, weekly_stats = calculate_schedule_stats(plan, recipe_map)
        except Exception as e:
            logger.error(f"Stats Calculation Error: {e}")
            raise HTTPException(status_code=500, detail=f"Stats Error: {str(e)}")

        # PERSISTENCE
        try:
            if req.user_id and req.week_id:
                supabase.table("schedules").upsert({
                    "user_id": req.user_id,
                    "week_id": req.week_id,
                    "schedule_json": plan
                }, on_conflict="user_id, week_id").execute()
        except Exception as e:
            logger.error(f"Persistence Error: {e}")
            # Don't fail the whole request for persistence, just log
            pass
    else:
        # No plan was found in the message
        raise HTTPException(status_code=422, detail="AI failed to generate a plan within <PLAN> tags. Try being more specific.")

    return {
        "suggested_plan": plan, 
        "recipes": recs if plan else [],
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats
    }

@app.post("/api/recipes/search")
def search_recipes(req: SearchRequest):
    idx_obj = get_pinecone_index()
    results = []
    if idx_obj:
        try:
            emb = get_embedding(req.query)
            res = idx_obj.query(vector=emb, top_k=req.limit, include_metadata=True)
            if res.get('matches'):
                for m in res['matches']:
                    results.append(repair_recipe(m['id'], m['metadata']))
        except Exception as e:
            logger.error(f"Manual search error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    return {"recipes": results}

import random

@app.get("/api/recommendations/{user_id}")
def get_recommendations(user_id: int):
    res_favs = supabase.table("favorites").select("recipe_id, recipe_data").eq("user_id", user_id).execute()
    favs = [r["recipe_data"] for r in res_favs.data] if res_favs.data else []
    q = " ".join({r.get("category","")+" "+r.get("cuisine","") for r in favs}).strip() or "healthy"
    
    fav_ids = [r.get("id") for r in favs]
    out = []
    idx_obj = get_pinecone_index()
    if idx_obj:
        emb = get_embedding(q)
        # Increase top_k to get a larger pool to sample from for refresh
        res = idx_obj.query(vector=emb, top_k=40, include_metadata=True)
        if res.get('matches'):
            candidates = []
            for m in res['matches']:
                if m['id'] in fav_ids: continue
                candidates.append(repair_recipe(m['id'], m['metadata']))
            
            # Shuffle candidates to ensure variety on refresh
            random.shuffle(candidates)
            out = candidates[:6]
    return {"recipes": out}

@app.post("/api/chat")
def chat(req: ChatRequest):
    recs = []
    ctx = ""
    try:
        idx_obj = get_pinecone_index()
        if idx_obj:
            try:
                emb = get_embedding(req.message)
                res = idx_obj.query(vector=emb, top_k=20, include_metadata=True)
                for m in res.get('matches', []):
                    if m['id'] in req.exclude_ids: continue
                    obj = repair_recipe(m['id'], m['metadata'])
                    recs.append(obj)
                    # Keep context simple: just name and ID
                    ctx += f"ID: {obj['id']} | {obj['name']}\n"
                    # Default to 5 max or as requested
                    if len(recs) >= (req.num_recipes or 5): break
            except Exception as se:
                logger.error(f"Search error: {se}")

        sys = (
            "You are NourishAI assistant, a helpful and premium healthy eating companion. "
            "Use <PLAN> tags for weekly meal plan JSON if the user asks for a plan or arrangement. "
            "If the user asks for more recipes, provide NEW ones from the context below. "
            "CRITICAL: Do not include JSON or backticks (```json) in your chat response text. "
            "CRITICAL: The chat response must be ONLY conversational text. No JSON outside <PLAN> tags. "
            "IMPORTANT: Use exactly these short keys for days: Mon, Tue, Wed, Thu, Fri, Sat, Sun. "
            "IMPORTANT: Use exactly these meal keys: Breakfast, Lunch, Dinner. "
            "IMPORTANT: The JSON values inside <PLAN> tags must be the Recipe IDs (UUIDs), NOT the names. "
            "IMPORTANT: Do not repeat the names of the dishes in your conversational text, as they are already visible as cards below. "
            "IMPORTANT: Never show Recipe IDs (UUID strings) to the user. Always refer to recipes by their names. "
            f"\nAvailable Recipes:\n{ctx}"
        )
        
        messages = [{"role":"system","content":sys}]
        for h in req.history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": req.message})
        
        # Robust LLM call with timeout and retries
        try:
            response = litellm.completion(
                model=DEFAULT_MODEL, 
                messages=messages,
                timeout=15.0,
                num_retries=2
            )
            msg = response.choices[0].message.content
        except Exception as llm_e:
            logger.error(f"LLM Failure: {llm_e}")
            return {
                "message": "I'm having a brief moment of brain fog! 🌬️ My AI brain couldn't reach the server. Please try again, and I'll be ready!", 
                "recipes": recs, # Still show the recipes from the successful search
                "suggested_plan": None
            }
        
        plan = None
        if "<PLAN>" in msg:
            try:
                parts = msg.split("<PLAN>")
                pre_text = parts[0].strip()
                after_part = parts[1].split("</PLAN>")
                plan_str = after_part[0].strip()
                post_text = after_part[1].strip() if len(after_part) > 1 else ""
                
                if "```" in plan_str:
                    plan_str = plan_str.split("```", 1)[1]
                    if plan_str.startswith("json"): plan_str = plan_str[4:]
                if plan_str.endswith("```"): plan_str = plan_str.rsplit("```", 1)[0].strip()
                
                raw_plan = json.loads(plan_str.strip())
                plan = normalize_plan(raw_plan, recs)
                
                # Combine text and remove any leftover markdown markers
                msg = (pre_text + "\n" + post_text).strip()
                if msg.endswith("```"): msg = msg.rsplit("```", 1)[0].strip()
            except Exception as e:
                logger.error(f"Chat Plan Parsing Error: {e}")
                # If parsing fails, try to at least remove the <PLAN> tags from message
                msg = msg.split("<PLAN>")[0].strip()
        
        # FINAL NAKED JSON FALLBACK: If AI returned raw JSON without tags
        if not plan and msg.strip().startswith("{") and msg.strip().endswith("}"):
            try:
                raw_plan = json.loads(msg.strip())
                plan = normalize_plan(raw_plan, recs)
                msg = "I've arranged a special meal plan for you! 🥗 You can apply it to your schedule using the button below."
            except: pass
        
        # Strip any remaining plan tags just in case
        if "<PLAN>" in msg: msg = msg.split("<PLAN>")[0].strip()
        if "</PLAN>" in msg: msg = msg.split("</PLAN>")[-1].strip()
        
        # Calculate stats if plan generated
        daily_stats = {}
        weekly_stats = {}
        if plan:
            recipe_map = {r["id"]: r for r in recs}
            try:
                daily_stats, weekly_stats = calculate_schedule_stats(plan, recipe_map)
            except Exception as e:
                logger.error(f"Chat Stats Calculation Error: {e}")
            
        return {"message": msg, "recipes": recs, "suggested_plan": plan, "daily_stats": daily_stats, "weekly_stats": weekly_stats}
    except Exception as fatal_e:
        logger.error(f"FATAL CHAT ERROR: {fatal_e}")
        return {"message": "Oops! Something went wrong on my side. 🛠️ I'm resetting and will be back for your next question!", "recipes": [], "suggested_plan": None}

    
@app.post("/api/grocery-list")
def get_grocery_list(req: GroceryRequest):
    schedule = req.schedule
    if not schedule:
        res = supabase.table("schedules").select("schedule_json").eq("user_id", req.user_id).eq("week_id", req.week_id).execute()
        if not res.data: return {"grocery_list": {}}
        schedule = res.data[0]["schedule_json"]
    
    recipe_ids = []
    for day in schedule.values():
        if isinstance(day, dict):
            for rid in day.values():
                if rid: recipe_ids.append(rid)
    
    if not recipe_ids: return {"grocery_list": {}}
    
    unique_recipe_ids = list(set(recipe_ids))
    all_ingredients = []
    idx_obj = get_pinecone_index()
    if idx_obj:
        try:
            fetch_res = idx_obj.fetch(ids=unique_recipe_ids)
            if fetch_res.get('vectors'):
                for v in fetch_res['vectors'].values():
                    meta = v['metadata']
                    ings = json.loads(meta.get("ingredients", "[]")) if isinstance(meta.get("ingredients"), str) else meta.get("ingredients", [])
                    all_ingredients.extend(ings)
        except: pass
    
    unit_system = req.unit_system or "imperial"
    unit_defs = "Imperial (lbs, oz, cups, tsp, tbsp)" if unit_system == "imperial" else "Metric (g, kg, ml, l)"

    # Use LLM to consolidate and truncate the list with strict instructions
    prompt = (
        f"You are a master grocery list optimizer. Consolidate the following raw ingredients into a PERFECT, professional grocery list in {unit_system} units. "
        f"MANDATORY UNIT SYSTEM: Use ONLY {unit_defs}. Convert any non-conforming units (e.g., if Imperial, convert 500g to lbs/oz; if Metric, convert cups to ml/l).\n"
        "STRATEGIC MANDATES:\n"
        "1. ABSOLUTELY NO DUPLICATES. If an item appears multiple times, sum their quantities accurately.\n"
        "2. CONSOLIDATE SIMILAR ITEMS: Combine 'cloves of garlic' and 'garlic cloves' into a single entry.\n"
        "3. SIMPLIFY: Convert complex measurements into the simplest form (e.g., '16 tbsp' to '1 cup').\n"
        "4. CATEGORIZE: Group items logically into categories like 'Produce', 'Meat', 'Dairy', 'Pantry', etc.\n"
        "5. TRUNCATE: Remove fluff like 'freshly ground' or 'to taste' unless critical.\n"
        "6. NO MARKDOWN: Absolutely no asterisks, backticks, bolding, or italics in the strings.\n"
        "7. STRICT QUANTITIES: Every item must have a clear numeric quantity and a standard unit. If count-based, just the number (e.g., '2 onions').\n"
        "8. OUTPUT FORMAT: Return a RAW JSON object where keys are category names and values are arrays of strings (the ingredients).\n\n"
        f"Ingredients: {json.dumps(all_ingredients)}"
    )
    
    try:
        response = litellm.completion(
            model=DEFAULT_MODEL, 
            messages=[{"role": "system", "content": f"You are a grocery API that returns ONLY raw JSON. You MUST use {unit_system} units exclusively."}, 
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=25.0
        )
        content = response.choices[0].message.content.strip()
        
        # Robust JSON extraction
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"): content = content[4:]
            content = content.split("```")[0].strip()
            
        data = json.loads(content)
        
        # Expecting { "Produce": ["1 onion", "2 carrots"], "Meat": ["500g chicken"] }
        if not isinstance(data, dict):
             return {"grocery_list": {"Other": [str(data)]}}
        
        return {"grocery_list": data}
    except Exception as e:
        logger.error(f"Grocery list error: {e}")
        # Simple fallback: unique items under "General"
        unique_ings = list(set([str(i) for i in all_ingredients]))
        return {"grocery_list": {"General": unique_ings}}

@app.post("/api/meal-prep-guide")
def get_meal_prep_guide(req: GroceryRequest):
    schedule = req.schedule
    if not schedule:
        res = supabase.table("schedules").select("schedule_json").eq("user_id", req.user_id).eq("week_id", req.week_id).execute()
        if not res.data: return {"guide": "No schedule found."}
        schedule = res.data[0]["schedule_json"]

    recipe_ids = []
    for day in schedule.values():
        if isinstance(day, dict):
            for rid in day.values():
                if rid: recipe_ids.append(rid)
    
    if not recipe_ids: return {"guide": "No recipes in schedule."}
    
    unique_ids = list(set(recipe_ids))
    recipe_meta = []
    idx_obj = get_pinecone_index()
    if idx_obj:
        try:
            fetch_res = idx_obj.fetch(ids=unique_ids)
            if fetch_res.get('vectors'):
                recipe_meta = [v['metadata'] for v in fetch_res['vectors'].values()]
        except: pass
    
    prep_context = ""
    for m in recipe_meta:
        title = m.get('title') or m.get('name') or "Recipe"
        prep_context += f"RECIPE: {title}\nINSTRUCTIONS: {m.get('instructions')}\n\n"

    prompt = (
        "You are a world-class meal prep consultant. Create a HIGHLY EFFICIENT, step-by-step 'Meal Prep Guide' for the entire week based on these recipes. "
        "Consolidate all tasks into a single master plan. Focus on saving time and minimizing cleanup.\n\n"
        "STRICT INSTRUCTIONS:\n"
        "1. Return a JSON object with a key 'guide' that contains a list of objects.\n"
        "2. Each object must have these keys: 'step' (integer), 'task' (string), 'meal_name' (string, list the specific meals this task applies to), 'efficiency_tip' (string).\n"
        "3. Group tasks chronologically: Preparations (chopping, washing) -> Cooking (boiling, roasting) -> Assembly/Storage.\n"
        "4. Combine tasks where possible (e.g., 'Chop all onions for both the Stew and the Curry').\n"
        "5. SPECIFICITY: Cooking tasks MUST include specific temperatures in BOTH Fahrenheit and Celsius (e.g., 400°F/200°C) and estimated durations (e.g., 45 minutes).\n"
        "6. DO NOT use any Markdown formatting (no asterisks, no bolding, no italics) in the text.\n"
        "7. COMMA SEPARATION: In the 'meal_name' field, if a task relates to multiple dishes, separate them with a comma (e.g., 'Bistek, Chicken Marengo').\n"
        f"Context:\n{prep_context}"
    )

    try:
        response = litellm.completion(
            model=DEFAULT_MODEL,
            messages=[{"role": "system", "content": "You MUST provide structured meal prep guides as a JSON object with a 'guide' key containing a list of objects. NO MARKDOWN."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        return {"guide": data.get("guide", [])}
    except Exception as e:
        logger.error(f"Meal prep error: {e}")
        return {"guide": []}

@app.get("/api/admin/pinecone-stats")
def get_pinecone_stats():
    idx_obj = get_pinecone_index()
    stats = {"error": "Pinecone not initialized"}
    if idx_obj:
        try:
            stats = idx_obj.describe_index_stats().to_dict()
        except Exception as e:
            stats = {"error": str(e)}
    
    return {
        "pinecone": stats,
        "api_keys": {
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
            "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY")),
            "PINECONE_API_KEY": bool(os.getenv("PINECONE_API_KEY")),
            "SUPABASE_URL": bool(os.getenv("SUPABASE_URL")),
            "SUPABASE_KEY": bool(os.getenv("SUPABASE_KEY"))
        },
        "openai_client_ready": bool(oa_client),
        "embedding_model": EMBEDDING_MODEL,
        "dimension": 1536
    }

if __name__ == "__main__":
    import uvicorn
    # Use reload=True to ensure code changes are picked up immediately
    uvicorn.run("api.index:app", host="127.0.0.1", port=8000, reload=True)
