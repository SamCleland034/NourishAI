import os
import uuid
import time
import json
import logging
import sqlite3
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

import chromadb
from chromadb.utils import embedding_functions
import litellm

# --- STATIC CONFIG ---
DATA_DIR = os.getenv("DATA_DIR", ".")
STATIC_DIR = os.path.join(DATA_DIR, "static")
IMAGES_DIR = os.path.join(STATIC_DIR, "recipe_images")
os.makedirs(IMAGES_DIR, exist_ok=True)

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

# --- Google OAuth Config ---
def find_client_secret():
    for f in os.listdir("."):
        if f.startswith("client_secret") and f.endswith(".json"):
            return f
    return "client_secret.json"

CLIENT_SECRET_FILE = find_client_secret()
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")

# --- SQLite Setup ---
DB_FILE = os.path.join(DATA_DIR, "users.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS favorites (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, recipe_id TEXT, recipe_data TEXT, UNIQUE(user_id, recipe_id), FOREIGN KEY(user_id) REFERENCES users(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedules (user_id INTEGER, week_id TEXT, schedule_json TEXT, PRIMARY KEY (user_id, week_id), FOREIGN KEY(user_id) REFERENCES users(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS google_tokens (user_id INTEGER PRIMARY KEY, token_json TEXT, FOREIGN KEY(user_id) REFERENCES users(id))''')
    conn.commit()
    conn.close()

init_db()

def ensure_local_image(rid, url, retries=2):
    """Downloads image if not exists and returns local URL path with retries."""
    if not url: return None
    
    # Create a safe filename
    ext = url.split('.')[-1] if '.' in url else 'jpg'
    if len(ext) > 4: ext = 'jpg'
    filename = f"{rid}.{ext}"
    local_path = os.path.join(IMAGES_DIR, filename)
    local_url = f"/static/recipe_images/{filename}"

    if os.path.exists(local_path):
        return local_url

    # Reuse or create a client with trust_env=True for proxy support
    with httpx.Client(trust_env=True, timeout=10.0) as client_http:
        for attempt in range(retries + 1):
            try:
                logger.info(f"Downloading image locally: {url} (Attempt {attempt+1})")
                with client_http.stream("GET", url, follow_redirects=True) as response:
                    if response.status_code == 200:
                        with open(local_path, 'wb') as f:
                            for chunk in response.iter_bytes():
                                f.write(chunk)
                        return local_url
                break # Non-retryable
            except Exception as e:
                if attempt == retries:
                    logger.error(f"Failed to download {url} after {retries+1} attempts: {e}")
                else:
                    time.sleep(1)
    
    return url # Fallback to original URL if download fails

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
    """Helper to ensure all required fields are present in a recipe object and images are local."""
    img = meta.get("image")
    title = meta.get("title", "Recipe")
    
    # Nutritional data from metadata or estimate
    nutri_str = meta.get("nutrition")
    if nutri_str:
        try: nutrition = json.loads(nutri_str)
        except: nutrition = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    else:
        # We don't want to call LLM every time in a loop. 
        # For this prototype, we'll use a fast heuristic or return 0s if not pre-calculated.
        # In a real app, you'd pre-calculate this during ingestion.
        nutrition = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

    # 1. Handle missing or placeholder images
    if not img or "via.placeholder" in img or "placehold.co" in img:
        img = f"https://placehold.co/600x400?text={title.replace(' ', '+')}"
    
    # 2. Ensure it's cached locally
    local_img = ensure_local_image(rid, img)
    
    return {
        "id": rid,
        "name": title,
        "category": meta.get("category"),
        "cuisine": meta.get("area"),
        "ingredients": json.loads(meta.get("ingredients", "[]")),
        "instructions": meta.get("instructions"),
        "image": local_img,
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Initialize ChromaDB
CHROMA_PATH = os.path.join(DATA_DIR, "chroma_db")
client = chromadb.PersistentClient(path=CHROMA_PATH)
emb_fn = embedding_functions.DefaultEmbeddingFunction()
collection = client.get_or_create_collection(name="recipes", embedding_function=emb_fn)

# --- MODELS ---
class AuthRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = []
    num_recipes: int = 3
    exclude_ids: List[str] = []

class GroceryRequest(BaseModel):
    user_id: int
    week_id: str
    schedule: Optional[Dict[str, Any]] = None

# --- MODELS CONFIG ---

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
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO google_tokens (user_id, token_json) VALUES (?, ?)", (user_id, flow.credentials.to_json()))
        conn.commit(); conn.close()
        return HTMLResponse("<h1>Success!</h1><script>setTimeout(()=>window.close(), 1500);</script>")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>")

@app.get("/api/google/status/{user_id}")
def get_google_status(user_id: int):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT user_id FROM google_tokens WHERE user_id = ?", (user_id,))
    res = c.fetchone(); conn.close()
    return {"connected": res is not None}

@app.post("/api/google/export")
def export_to_calendar(req: ScheduleRequest):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT token_json FROM google_tokens WHERE user_id = ?", (req.user_id,))
        row = c.fetchone(); conn.close()
        if not row: raise HTTPException(status_code=401, detail="Not connected")
        
        creds = Credentials.from_authorized_user_info(json.loads(row[0]), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            conn = sqlite3.connect(DB_FILE); c = conn.cursor()
            c.execute("UPDATE google_tokens SET token_json = ? WHERE user_id = ?", (creds.to_json(), req.user_id))
            conn.commit(); conn.close()

        service = build('calendar', 'v3', credentials=creds)
        year, week = map(int, req.week_id.split("-W"))
        # Robust Sunday calculation
        start_date = datetime.datetime.strptime(f'{year}-W{week}-0', "%Y-W%W-%w").date()
        
        day_offsets = {"Sun": 0, "Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6}
        meal_times = {"Breakfast": "08:00:00", "Lunch": "12:00:00", "Dinner": "19:00:00"}

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT recipe_id, recipe_data FROM favorites WHERE user_id = ?", (req.user_id,))
        fav_map = {r[0]: json.loads(r[1]) for r in c.fetchall()}; conn.close()

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

# --- APP API ---
@app.post("/api/auth/signup")
def signup(req: AuthRequest):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (req.username, hash_password(req.password)))
        uid = c.lastrowid; conn.commit(); return {"user_id": uid, "username": req.username}
    except: raise HTTPException(status_code=400, detail="Taken")
    finally: conn.close()

@app.post("/api/auth/login")
def login(req: AuthRequest):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE username = ? AND password_hash = ?", (req.username, hash_password(req.password)))
    u = c.fetchone(); conn.close()
    if u: return {"user_id": u[0], "username": u[1]}
    raise HTTPException(status_code=401, detail="Error")

@app.post("/api/favorites")
def add_favorite(req: FavoriteRequest):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO favorites (user_id, recipe_id, recipe_data) VALUES (?, ?, ?)", (req.user_id, req.recipe.get("id"), json.dumps(req.recipe)))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/favorites/remove")
def remove_favorite(req: FavoriteRequest):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("DELETE FROM favorites WHERE user_id = ? AND recipe_id = ?", (req.user_id, req.recipe.get("id")))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/favorites/{user_id}")
def get_favorites(user_id: int):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT recipe_data FROM favorites WHERE user_id = ?", (user_id,))
    rows = c.fetchall(); conn.close()
    recipes = [json.loads(r[0]) for r in rows]
    
    repaired = []
    for r in recipes:
        if not r.get("image") or "via.placeholder" in r.get("image", ""):
            res = collection.get(ids=[r.get("id")], include=["metadatas"])
            if res['metadatas']:
                repaired.append(repair_recipe(r.get("id"), res['metadatas'][0]))
            else:
                # Fallback
                r["image"] = f"https://placehold.co/600x400?text={r.get('name', 'Recipe').replace(' ', '+')}"
                repaired.append(r)
        else:
            repaired.append(r)
    return {"recipes": repaired}

@app.post("/api/schedule")
def save_schedule(req: ScheduleRequest):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO schedules (user_id, week_id, schedule_json) VALUES (?, ?, ?)", (req.user_id, req.week_id, json.dumps(req.schedule)))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/schedule/{user_id}/{week_id}")
def get_schedule(user_id: int, week_id: str):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    # Try specific week first
    c.execute("SELECT schedule_json FROM schedules WHERE user_id = ? AND week_id = ?", (user_id, week_id))
    r = c.fetchone()
    
    # Fallback to recurring if not found
    is_recurring_applied = False
    if not r:
        c.execute("SELECT schedule_json FROM schedules WHERE user_id = ? AND week_id = 'recurring'", (user_id,))
        r = c.fetchone()
        if r: is_recurring_applied = True
    
    conn.close()
    schedule = json.loads(r[0]) if r else {}
    
    recipe_ids = set()
    for day in schedule.values():
        if isinstance(day, dict):
            for rid in day.values():
                if rid: recipe_ids.add(rid)
    
    recipe_map = {}
    daily_stats = {d: {"calories": 0, "protein": 0, "carbs": 0, "fat": 0} for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]}
    weekly_stats = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

    if recipe_ids:
        res = collection.get(ids=list(recipe_ids), include=["metadatas"])
        for i, rid in enumerate(res['ids']):
            repaired = repair_recipe(rid, res['metadatas'][i])
            recipe_map[rid] = repaired
            
    daily_stats, weekly_stats = calculate_schedule_stats(schedule, recipe_map)

    return {
        "schedule": schedule, 
        "recipes": recipe_map, 
        "is_recurring_applied": is_recurring_applied,
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats
    }

class UserOnlyRequest(BaseModel):
    user_id: int

@app.post("/api/planner/autofill")
def autofill_planner(req: UserOnlyRequest):
    # Logic: Get favorites to find preferences, then query DB for 21 diverse recipes
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT recipe_data FROM favorites WHERE user_id = ?", (req.user_id,))
    rows = c.fetchall(); conn.close()
    favs = [json.loads(r[0]) for r in rows]
    
    # Build a query from favorites
    q = " ".join({r.get("category","")+" "+r.get("cuisine","") for r in favs}).strip() or "healthy delicious recipes"
    
    # Get a large pool from Chroma
    res = collection.query(query_texts=[q], n_results=40)
    pool = []
    if res['metadatas']:
        for i, m in enumerate(res['metadatas'][0]):
            pool.append(repair_recipe(res['ids'][0][i], m))
    
    import random
    if len(pool) < 21:
        # Emergency backup peek
        res_backup = collection.peek(limit=21)
        pool.extend([repair_recipe(res_backup['ids'][i], m) for i, m in enumerate(res_backup['metadatas'])])
    
    random.shuffle(pool)
    
    new_schedule = {}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    meals = ["Breakfast", "Lunch", "Dinner"]
    
    idx = 0
    for d in days:
        new_schedule[d] = {}
        for m in meals:
            # Try to pick a recipe that fits the meal type if category exists
            picked = pool[idx % len(pool)]
            # Simple heuristic: if it's breakfast, try to find a breakfast category in the next few items
            if m == "Breakfast":
                for search_idx in range(idx, idx + 5):
                    candidate = pool[search_idx % len(pool)]
                    if candidate.get("category") == "Breakfast":
                        picked = candidate
                        break
            
            new_schedule[d][m] = picked.get("id")
            idx += 1
            
    # Also return the full metadata for these recipes so frontend can display them
    recipe_map = {r["id"]: r for r in pool}
    daily_stats, weekly_stats = calculate_schedule_stats(new_schedule, recipe_map)

    return {
        "schedule": new_schedule, 
        "recipes": recipe_map,
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats
    }

@app.post("/api/planner/prompt")
def planner_prompt(req: ChatRequest):
    # Similar to chat but specialized for arrangement
    res = collection.query(
        query_texts=[req.message], 
        n_results=15,
        where={"id": {"$nin": req.exclude_ids}} if req.exclude_ids else None
    )
    recs = []
    ctx = ""
    if res['metadatas']:
        for i, m in enumerate(res['metadatas'][0]):
            obj = repair_recipe(res['ids'][0][i], m)
            recs.append(obj); ctx += f"ID: {obj['id']} | {obj['name']} ({obj['category']})\n"
    
    sys = (
        "You are a meal planner assistant. Arrange a 7-day schedule (Mon-Sun, Breakfast/Lunch/Dinner) based on the user request. "
        "Use ONLY the recipe IDs provided below. Return a valid JSON within <PLAN> tags. "
        "IMPORTANT: Never show the Recipe IDs (UUIDs) to the user in your response. Only use them inside the <PLAN> tags."
        f"\nRecipes:\n{ctx}"
    )
    response = litellm.completion(model=DEFAULT_MODEL, messages=[{"role":"system","content":sys}, {"role":"user","content":req.message}])
    msg = response.choices[0].message.content
    
    plan = None
    if "<PLAN>" in msg:
        try:
            plan_str = msg.split("<PLAN>")[1].split("</PLAN>")[0]
            plan = json.loads(plan_str)
        except: pass
        
    # Calculate stats if plan generated
    daily_stats = None
    weekly_stats = None
    if plan:
        recipe_map = {r["id"]: r for r in recs}
        daily_stats, weekly_stats = calculate_schedule_stats(plan, recipe_map)

    return {
        "suggested_plan": plan, 
        "recipes": recs if plan else [],
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats
    }

@app.get("/api/recommendations/{user_id}")
def get_recommendations(user_id: int):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT recipe_data FROM favorites WHERE user_id = ?", (user_id,))
    rows = c.fetchall(); conn.close(); favs = [json.loads(r[0]) for r in rows]
    q = " ".join({r.get("category","")+" "+r.get("cuisine","") for r in favs}).strip() or "healthy"
    
    # Exclude favorites from recommendations
    fav_ids = [r.get("id") for r in favs]
    res = collection.query(
        query_texts=[q], 
        n_results=6,
        where={"id": {"$nin": fav_ids}} if fav_ids else None
    )
    out = []
    if res['metadatas']:
        for i, m in enumerate(res['metadatas'][0]):
            out.append(repair_recipe(res['ids'][0][i], m))
    return {"recipes": out}

@app.post("/api/chat")
def chat(req: ChatRequest):
    # Use exclude_ids to avoid repetitive results in the same conversation
    res = collection.query(
        query_texts=[req.message], 
        n_results=10,
        where={"id": {"$nin": req.exclude_ids}} if req.exclude_ids else None
    )
    recs = []
    ctx = ""
    if res['metadatas']:
        for i, m in enumerate(res['metadatas'][0]):
            obj = repair_recipe(res['ids'][0][i], m)
            recs.append(obj); ctx += f"ID: {obj['id']} | {obj['name']}\n"
            
    sys = (
        "You are NourishAI assistant, a helpful and premium healthy eating companion. "
        "Use <PLAN> tags for weekly meal plan JSON. If the user asks for more recipes, provide NEW ones from the context below. "
        "IMPORTANT: Never show the Recipe IDs (UUID strings) to the user. Always refer to recipes by their names. "
        f"Current Recipes in Context:\n{ctx}"
    )
    
    messages = [{"role":"system","content":sys}]
    for h in req.history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": req.message})
    
    response = litellm.completion(model=DEFAULT_MODEL, messages=messages)
    msg = response.choices[0].message.content
    plan = None
    if "<PLAN>" in msg:
        try:
            plan = json.loads(msg.split("<PLAN>")[1].split("</PLAN>")[0])
            msg = msg.split("<PLAN>")[0].strip()
        except: pass
    return {"message": msg, "recipes": recs if plan else recs[:req.num_recipes], "suggested_plan": plan}

@app.post("/api/grocery-list")
def get_grocery_list(req: GroceryRequest):
    schedule = req.schedule
    if not schedule:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT schedule_json FROM schedules WHERE user_id = ? AND week_id = ?", (req.user_id, req.week_id))
        row = c.fetchone()
        if not row:
            return {"grocery_list": []}
        schedule = json.loads(row[0])
    
    recipe_ids = []
    for day in schedule.values():
        if isinstance(day, dict):
            for rid in day.values():
                if rid: recipe_ids.append(rid)
    
    if not recipe_ids:
        return {"grocery_list": []}
    
    # Ensure unique IDs to avoid chromadb.errors.DuplicateIDError
    unique_recipe_ids = list(set(recipe_ids))
    res = collection.get(ids=unique_recipe_ids, include=["metadatas"])
    all_ingredients = []
    for m in res['metadatas']:
        ings = json.loads(m.get("ingredients", "[]"))
        all_ingredients.extend(ings)
    
    # Use LLM to consolidate and truncate the list with strict instructions
    prompt = (
        "You are a master grocery list optimizer. Consolidate the following raw ingredients into a PERFECT, professional grocery list. "
        "STRATEGIC MANDATES:\n"
        "1. ABSOLUTELY NO DUPLICATES. If an item appears multiple times, sum their quantities accurately.\n"
        "2. CONSOLIDATE SIMILAR ITEMS: Combine 'cloves of garlic' and 'garlic cloves' into a single entry.\n"
        "3. SIMPLIFY: Convert complex measurements into the simplest form (e.g., '4 units of 1/4 cup' to '1 cup').\n"
        "4. CATEGORIZE: Group items logically (Produce, Meat, Dairy, Pantry).\n"
        "5. TRUNCATE: Remove fluff like 'freshly ground' or 'to taste' unless critical.\n"
        "6. NO MARKDOWN: Absolutely no asterisks, bolding, or italics in the strings.\n"
        "7. STRICT QUANTITIES: Every item must have a clear numeric quantity and a standard unit (e.g., '500g', '2 cups', '3 cloves'). If count-based, just the number (e.g., '2 onions').\n"
        "8. NO FUZZY TERMS: NEVER use 'as needed', 'to taste', or other non-numeric descriptors. If a quantity is unknown, provide a reasonable estimate for a single purchase.\n\n"
        f"Return a JSON array of strings. Ingredients: {json.dumps(all_ingredients)}"
    )
    
    try:
        response = litellm.completion(
            model=DEFAULT_MODEL, 
            messages=[{"role": "system", "content": "You only output valid JSON arrays of strings."}, 
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        
        final_list = []
        if isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    final_list = val
                    break
        elif isinstance(data, list):
            final_list = data

        # Secondary strict deduplication fallback (case-insensitive)
        seen = set()
        deduped = []
        for item in final_list:
            clean = str(item).strip().lower()
            if clean not in seen:
                deduped.append(str(item).strip())
                seen.add(clean)
        
        return {"grocery_list": deduped if deduped else ["No ingredients found after consolidation."]}
    except Exception as e:
        logger.error(f"Grocery list error: {e}")
        # Simple fallback: unique items
        unique_ings = list(set([str(i) for i in all_ingredients]))
        return {"grocery_list": unique_ings}

@app.post("/api/meal-prep-guide")
def get_meal_prep_guide(req: GroceryRequest):
    schedule = req.schedule
    if not schedule:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT schedule_json FROM schedules WHERE user_id = ? AND week_id = ?", (req.user_id, req.week_id))
        row = c.fetchone()
        if not row: return {"guide": "No schedule found."}
        schedule = json.loads(row[0])

    recipe_ids = []
    for day in schedule.values():
        if isinstance(day, dict):
            for rid in day.values():
                if rid: recipe_ids.append(rid)
    
    if not recipe_ids: return {"guide": "No recipes in schedule."}
    
    unique_ids = list(set(recipe_ids))
    res = collection.get(ids=unique_ids, include=["metadatas"])
    
    prep_context = ""
    for i, m in enumerate(res['metadatas']):
        prep_context += f"RECIPE: {m.get('title')}\nINSTRUCTIONS: {m.get('instructions')}\n\n"

    prompt = (
        "You are a world-class meal prep consultant. Create a HIGHLY EFFICIENT, step-by-step 'Meal Prep Guide' for the entire week based on these recipes. "
        "Consolidate all tasks into a single master plan. Focus on saving time and minimizing cleanup.\n\n"
        "STRICT INSTRUCTIONS:\n"
        "1. Return a JSON object with a key 'guide' that contains a list of objects.\n"
        "2. Each object must have these keys: 'step' (integer), 'task' (string), 'meal_name' (string, list the specific meals this task applies to), 'efficiency_tip' (string).\n"
        "3. Group tasks chronologically: Preparations (chopping, washing) -> Cooking (boiling, roasting) -> Assembly/Storage.\n"
        "4. Combine tasks where possible (e.g., 'Chop all onions for both the Stew and the Curry').\n"
        "5. DO NOT use any Markdown formatting (no asterisks, no bolding, no italics) in the text.\n"
        "6. COMMA SEPARATION: In the 'meal_name' field, if a task relates to multiple dishes, separate them with a comma (e.g., 'Bistek, Chicken Marengo').\n"
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

if __name__ == "__main__":
    import uvicorn
    # Use reload=True to ensure code changes are picked up immediately
    uvicorn.run("nourish_backend:app", host="127.0.0.1", port=8000, reload=True)
