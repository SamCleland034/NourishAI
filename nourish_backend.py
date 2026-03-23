import os
import uuid
import json
import logging
import sqlite3
import hashlib
import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from recipe_scrapers import scrape_me

import chromadb
from chromadb.utils import embedding_functions
import litellm

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

# --- Google OAuth Config ---
def find_client_secret():
    for f in os.listdir("."):
        if f.startswith("client_secret") and f.endswith(".json"):
            return f
    return "client_secret.json"

CLIENT_SECRET_FILE = find_client_secret()
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
REDIRECT_URI = "http://127.0.0.1:8000/api/auth/google/callback"

# --- SQLite Setup ---
DB_FILE = "users.db"

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

def repair_recipe(rid, meta):
    """Helper to ensure all required fields are present in a recipe object."""
    img = meta.get("image")
    # If image is missing or is an old broken placeholder, fix it
    if not img or "via.placeholder" in img:
        title = meta.get("title", "Recipe")
        img = f"https://placehold.co/600x400?text={title.replace(' ', '+')}"
    
    return {
        "id": rid,
        "name": meta.get("title"),
        "category": meta.get("category"),
        "cuisine": meta.get("area"),
        "ingredients": json.loads(meta.get("ingredients", "[]")),
        "instructions": meta.get("instructions"),
        "image": img
    }

app = FastAPI(title="NourishAI Backend")

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
client = chromadb.PersistentClient(path="./chroma_db")
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
    if recipe_ids:
        res = collection.get(ids=list(recipe_ids), include=["metadatas"])
        for i, rid in enumerate(res['ids']):
            recipe_map[rid] = repair_recipe(rid, res['metadatas'][i])
            
    return {"schedule": schedule, "recipes": recipe_map, "is_recurring_applied": is_recurring_applied}

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
    return {"schedule": new_schedule, "recipes": recipe_map}

@app.post("/api/planner/prompt")
def planner_prompt(req: ChatRequest):
    # Similar to chat but specialized for arrangement
    res = collection.query(query_texts=[req.message], n_results=15)
    recs = []
    ctx = ""
    for i, m in enumerate(res['metadatas'][0]):
        obj = repair_recipe(res['ids'][0][i], m)
        recs.append(obj); ctx += f"ID: {obj['id']} | {obj['name']} ({obj['category']})\n"
    
    sys = f"You are a meal planner. Arrange a 7-day schedule (Mon-Sun, Breakfast/Lunch/Dinner) based on the user request. Use ONLY the recipe IDs provided below. Return a valid JSON within <PLAN> tags.\nRecipes:\n{ctx}"
    response = litellm.completion(model="gpt-4o-mini", messages=[{"role":"system","content":sys}, {"role":"user","content":req.message}])
    msg = response.choices[0].message.content
    
    plan = None
    if "<PLAN>" in msg:
        try:
            plan = json.loads(msg.split("<PLAN>")[1].split("</PLAN>")[0])
        except: pass
        
    return {"suggested_plan": plan, "recipes": recs if plan else []}

@app.get("/api/recommendations/{user_id}")
def get_recommendations(user_id: int):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT recipe_data FROM favorites WHERE user_id = ?", (user_id,))
    rows = c.fetchall(); conn.close(); favs = [json.loads(r[0]) for r in rows]
    q = " ".join({r.get("category","")+" "+r.get("cuisine","") for r in favs}).strip() or "healthy"
    res = collection.query(query_texts=[q], n_results=6)
    out = []
    if res['metadatas']:
        for i, m in enumerate(res['metadatas'][0]):
            out.append(repair_recipe(res['ids'][0][i], m))
    return {"recipes": out}

@app.post("/api/chat")
def chat(req: ChatRequest):
    res = collection.query(query_texts=[req.message], n_results=10)
    recs = []
    ctx = ""
    for i, m in enumerate(res['metadatas'][0]):
        obj = repair_recipe(res['ids'][0][i], m)
        recs.append(obj); ctx += f"ID: {obj['id']} | {obj['name']}\n"
    sys = f"You are NourishAI assistant. Use <PLAN> tags for weekly meal plan JSON.\nRecipes:\n{ctx}"
    response = litellm.completion(model="gpt-4o-mini", messages=[{"role":"system","content":sys}] + [{"role":h["role"],"content":h["content"]} for h in req.history] + [{"role":"user","content":req.message}])
    msg = response.choices[0].message.content
    plan = None
    if "<PLAN>" in msg:
        try:
            plan = json.loads(msg.split("<PLAN>")[1].split("</PLAN>")[0])
            msg = msg.split("<PLAN>")[0].strip()
        except: pass
    return {"message": msg, "recipes": recs if plan else recs[:req.num_recipes], "suggested_plan": plan}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
