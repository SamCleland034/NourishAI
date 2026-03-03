import { useState, useEffect, useRef } from "react";

const CLAUDE_MODEL = "claude-sonnet-4-20250514";
const BACKEND_URL = "http://127.0.0.1:8000/api";

const RECIPE_DB = [
  { id: 1, name: "Grilled Salmon", cuisine: "American", tags: ["high-protein", "pescatarian"], time: 25, calories: 420, ingredients: [{ item: "salmon fillet", qty: "2", unit: "pieces" }, { item: "lemon", qty: "1", unit: "whole" }, { item: "olive oil", qty: "2", unit: "tbsp" }] },
  { id: 2, name: "Chicken Stir Fry", cuisine: "Asian", tags: ["high-protein", "low-carb", "quick"], time: 20, calories: 380, ingredients: [{ item: "chicken breast", qty: "1.5", unit: "lbs" }, { item: "broccoli", qty: "2", unit: "cups" }, { item: "bell peppers", qty: "2", unit: "whole" }] },
];

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const MEAL_TYPES = ["Breakfast", "Lunch", "Dinner"];

function retrieveRecipesLocal(prefs) {
  const { dietary = [], maxTime = 60 } = prefs;
  const filtered = RECIPE_DB.filter(r => {
    if (r.time > maxTime) return false;
    if (dietary.length > 0 && !dietary.some(d => r.tags.includes(d))) return false;
    return true;
  });
  return filtered.length > 2 ? filtered : RECIPE_DB;
}

const css = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #080d08; }
  ::-webkit-scrollbar { width: 6px; } 
  ::-webkit-scrollbar-track { background: #0d1a0d; }
  ::-webkit-scrollbar-thumb { background: #2d4a2d; border-radius: 3px; }
  .tag { transition: all 0.15s; }
  .tag:hover { border-color: #5a8a5a !important; }
  .nav-btn { transition: all 0.2s; }
  .nav-btn:hover { border-color: #5a8a5a !important; color: #9aaa9a !important; }
  .meal-cell-empty:hover { border-color: #3a6a3a !important; background: #0f220f !important; }
  .delivery-card:hover { border-color: #3a6a3a !important; }
  .quick-btn:hover { border-color: #3a5a3a !important; color: #9ab09a !important; background: #0d1a0d !important; }
  .recipe-option:hover { background: #1a2e1a !important; }
  .primary-btn:hover { background: #3a7a3a !important; }
  .check-btn:hover { background: #0d1a0d !important; border-color: #3a5a3a !important; }
  .hero-card:hover { border-color: #3a7a3a !important; transform: translateY(-2px); }
`;

export default function App() {
  const [tab, setTab] = useState("home");
  const [prefs, setPrefs] = useState({ name: "", dietary: [], cuisines: [], maxTime: 45, servings: 2, budget: "moderate" });
  const [mealPlan, setMealPlan] = useState({});
  const [groceryList, setGroceryList] = useState([]);
  const [chat, setChat] = useState([{ role: "assistant", content: "Hi! I am your AI meal planning assistant. Tell me your dietary preferences, ask for recipe ideas, or paste a recipe URL for me to scrape!" }]);
  const [chatInput, setChatInput] = useState("");
  const [scrapeUrl, setScrapeUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [generatingPlan, setGeneratingPlan] = useState(false);
  const chatRef = useRef(null);
  const DIETARY = ["vegan", "vegetarian", "pescatarian", "high-protein", "low-carb", "budget-friendly"];
  const CUISINES = ["American", "Asian", "Mediterranean", "Italian", "Mexican", "Californian"];

  useEffect(() => { if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight; }, [chat]);

  const T = {
    app: { minHeight: "100vh", background: "#080d08", fontFamily: "Georgia, 'Times New Roman', serif", color: "#e0d8c8" },
    hdr: { background: "linear-gradient(135deg,#162616,#0c1c0c)", borderBottom: "1px solid #243824", padding: "20px 36px", display: "flex", alignItems: "center", justifyContent: "space-between" },
    logo: { fontSize: "24px", fontWeight: "700", color: "#6ec86e", letterSpacing: "-0.5px" },
    logosub: { fontSize: "10px", color: "#4a7a4a", letterSpacing: "3px", textTransform: "uppercase", marginTop: "2px" },
    main: { maxWidth: "1280px", margin: "0 auto", padding: "36px 24px" },
    card: { background: "#0f180f", border: "1px solid #1c301c", borderRadius: "14px", padding: "24px", marginBottom: "18px" },
    ct: { fontSize: "11px", letterSpacing: "2.5px", textTransform: "uppercase", color: "#4a7a4a", marginBottom: "18px" },
    lbl: { display: "block", fontSize: "11px", color: "#4a7a4a", letterSpacing: "1.5px", textTransform: "uppercase", marginBottom: "6px", marginTop: "14px" },
    inp: { width: "100%", background: "#0c170c", border: "1px solid #263826", borderRadius: "7px", padding: "9px 13px", color: "#e0d8c8", fontSize: "13px", outline: "none" },
    sel: { width: "100%", background: "#0c170c", border: "1px solid #263826", borderRadius: "7px", padding: "9px 13px", color: "#e0d8c8", fontSize: "13px", outline: "none", cursor: "pointer" },
    mc: (filled) => ({ background: filled ? "#101e10" : "#0c170c", border: `1px solid ${filled ? "#263826" : "#1a2e1a"}`, borderRadius: "9px", padding: "9px 11px", minHeight: "68px", position: "relative", cursor: filled ? "default" : "pointer" }),
    cb: (role) => ({ maxWidth: "82%", padding: "11px 15px", borderRadius: role === "user" ? "14px 14px 3px 14px" : "14px 14px 14px 3px", background: role === "user" ? "#192e19" : "#131c13", border: `1px solid ${role === "user" ? "#263826" : "#1c2e1c"}`, alignSelf: role === "user" ? "flex-end" : "flex-start", fontSize: "13px", lineHeight: "1.6", color: "#ccd8cc" }),
  };

  async function updateGroceryList(planData) {
    try {
      const res = await fetch(`${BACKEND_URL}/grocery-list`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: planData })
      });
      if (res.ok) {
        const data = await res.json();
        setGroceryList(data.grocery_list || []);
      }
    } catch (err) {
      console.error("Backend grocery list error", err);
    }
  }

  async function generateMealPlan() {
    setGeneratingPlan(true);
    let plan = {};
    try {
      const res = await fetch(`${BACKEND_URL}/recommend`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: prefs })
      });
      let avail = RECIPE_DB;
      if (res.ok) {
        const data = await res.json();
        if (data.recipes && data.recipes.length > 0) avail = data.recipes;
      }
      DAYS.forEach(day => { 
        plan[day] = {}; 
        MEAL_TYPES.forEach(m => { 
          plan[day][m] = avail[Math.floor(Math.random() * avail.length)]; 
        }); 
      });
    } catch {
      const avail2 = retrieveRecipesLocal(prefs);
      DAYS.forEach(day => { 
        plan[day] = {}; 
        MEAL_TYPES.forEach(m => { 
          plan[day][m] = avail2[Math.floor(Math.random() * avail2.length)]; 
        }); 
      });
    }
    setMealPlan(plan); 
    await updateGroceryList(plan);
    setGeneratingPlan(false);
    setTab("planner");
  }

  async function handleScrape() {
    if (!scrapeUrl) return;
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/scrape`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: scrapeUrl })
      });
      const data = await res.json();
      if (res.ok) {
        alert("Scraped successfully! Added " + data.title + " to vector DB.");
        setScrapeUrl("");
      } else {
        alert("Error: " + data.detail);
      }
    } catch(err) {
      alert("Error calling backend scraper.");
    }
    setLoading(false);
  }

  async function sendChat() {
    if (!chatInput.trim() || loading) return;
    const msg = chatInput.trim(); setChatInput("");
    const hist = [...chat, { role: "user", content: msg }];
    setChat(hist); setLoading(true);
    setTimeout(() => {
      setChat([...hist, { role: "assistant", content: "I've noted that! You can try using the 'Generate AI Meal Plan' button to see how your preferences update your recommendations based on our retrieved recipe embeddings." }]);
      setLoading(false);
    }, 800);
  }

  function assignMeal(day, mealType, recipe) {
    const updated = { ...mealPlan, [day]: { ...mealPlan[day], [mealType]: recipe } };
    setMealPlan(updated); 
    updateGroceryList(updated);
  }

  const meals = Object.values(mealPlan).flatMap(d => Object.values(d)).filter(Boolean);
  const totalCal = meals.reduce((s, r) => s + (r.calories || 0), 0);

  return (
    <div style={T.app}>
      <style>{css}</style>
      <div style={T.hdr}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ fontSize: "28px" }}>🌿</span>
          <div style={{ cursor:"pointer" }} onClick={()=>setTab("home")}><div style={T.logo}>NourishAI</div><div style={T.logosub}>Intelligent Meal Planning</div></div>
        </div>
        <div style={{ display: "flex", gap: "7px" }}>
          {[["home","🏠 Home"],["planner","📅 Planner"],["grocery","🛒 Grocery"],["assistant","🤖 Assistant"]].map(([t,label]) => (
            <button key={t} className="nav-btn" onClick={() => setTab(t)} style={{ padding: "7px 18px", borderRadius: "18px", border: tab===t ? "1px solid #6ec86e" : "1px solid #263826", background: tab===t ? "#192e19" : "transparent", color: tab===t ? "#6ec86e" : "#6a8a6a", cursor: "pointer", fontSize: "12px", letterSpacing: "0.3px" }}>{label}</button>
          ))}
        </div>
      </div>

      <div style={T.main}>

        {tab === "home" && (
          <div style={{ textAlign:"center", padding:"40px 0" }}>
            <div style={{ fontSize:"48px", fontWeight:"800", color:"#6ec86e", marginBottom:"10px", letterSpacing:"-1px" }}>Welcome to NourishAI</div>
            <div style={{ fontSize:"18px", color:"#4a7a4a", marginBottom:"40px", maxWidth:"600px", margin:"0 auto 40px auto" }}>Your intelligent RAG-powered companion for meal planning, automated grocery lists, and instant delivery.</div>
            
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(300px, 1fr))", gap:"20px", marginBottom:"40px" }}>
              <div className="hero-card" style={{ ...T.card, cursor:"pointer", transition:"all 0.2s" }} onClick={()=>setTab("planner")}>
                <div style={{ fontSize:"32px", marginBottom:"15px" }}>📅</div>
                <div style={{ fontSize:"18px", fontWeight:"600", color:"#b8d0b8", marginBottom:"8px" }}>Smart Planner</div>
                <div style={{ fontSize:"13px", color:"#4a6a4a" }}>Generate a full 7-day meal plan based on your unique dietary preferences and cook-time constraints.</div>
              </div>
              <div className="hero-card" style={{ ...T.card, cursor:"pointer", transition:"all 0.2s" }} onClick={()=>setTab("grocery")}>
                <div style={{ fontSize:"32px", marginBottom:"15px" }}>🛒</div>
                <div style={{ fontSize:"18px", fontWeight:"600", color:"#b8d0b8", marginBottom:"8px" }}>Auto-Grocery</div>
                <div style={{ fontSize:"13px", color:"#4a6a4a" }}>Automatically aggregate ingredients and search Instacart or Amazon Fresh with a single click.</div>
              </div>
              <div className="hero-card" style={{ ...T.card, cursor:"pointer", transition:"all 0.2s" }} onClick={()=>setTab("assistant")}>
                <div style={{ fontSize:"32px", marginBottom:"15px" }}>🤖</div>
                <div style={{ fontSize:"18px", fontWeight:"600", color:"#b8d0b8", marginBottom:"8px" }}>AI Assistant</div>
                <div style={{ fontSize:"13px", color:"#4a6a4a" }}>Ask questions about nutrition, substitutions, or scrape new recipes directly from the web into your database.</div>
              </div>
            </div>

            <div style={{ ...T.card, maxWidth:"800px", margin:"0 auto", background:"linear-gradient(135deg,#0c1c0c,#162616)" }}>
              <div style={T.ct}>🚀 Quick Start</div>
              <div style={{ display:"flex", gap:"10px", justifyContent:"center" }}>
                <button className="primary-btn" onClick={()=>{setTab("planner")}} style={{ padding:"12px 30px", borderRadius:"8px", border:"none", background:"#2a6a2a", color:"#c0e0c0", cursor:"pointer", fontSize:"14px", fontWeight:"600" }}>Set Preferences</button>
                <button className="check-btn" onClick={()=>setTab("assistant")} style={{ padding:"12px 30px", borderRadius:"8px", border:"1px solid #263826", background:"transparent", color:"#6a8a6a", cursor:"pointer", fontSize:"14px" }}>Scrape a Recipe</button>
              </div>
            </div>
          </div>
        )}

        {tab === "planner" && (
          <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "24px", alignItems: "start" }}>
            <div>
              <div style={T.card}>
                <div style={T.ct}>⚙️ Your Preferences</div>
                <label style={T.lbl}>Dietary</label>
                <div style={{ display:"flex", flexWrap:"wrap", gap:"6px", marginTop:"4px" }}>
                  {DIETARY.map(d => <span key={d} className="tag" onClick={() => setPrefs(p=>({...p,dietary:p.dietary.includes(d)?p.dietary.filter(x=>x!==d):[...p.dietary,d]}))} style={{ padding:"4px 11px", borderRadius:"10px", fontSize:"11px", cursor:"pointer", border: prefs.dietary.includes(d)?"1px solid #6ec86e":"1px solid #263826", background: prefs.dietary.includes(d)?"#192e19":"transparent", color: prefs.dietary.includes(d)?"#6ec86e":"#4a6a4a" }}>{d}</span>)}
                </div>
                <label style={T.lbl}>Cuisines</label>
                <div style={{ display:"flex", flexWrap:"wrap", gap:"6px", marginTop:"4px" }}>
                  {CUISINES.map(c => <span key={c} className="tag" onClick={() => setPrefs(p=>({...p,cuisines:p.cuisines.includes(c)?p.cuisines.filter(x=>x!==c):[...p.cuisines,c]}))} style={{ padding:"4px 11px", borderRadius:"10px", fontSize:"11px", cursor:"pointer", border: prefs.cuisines.includes(c)?"1px solid #6ec86e":"1px solid #263826", background: prefs.cuisines.includes(c)?"#192e19":"transparent", color: prefs.cuisines.includes(c)?"#6ec86e":"#4a6a4a" }}>{c}</span>)}
                </div>
                <label style={T.lbl}>Max Cook Time</label>
                <select style={T.sel} value={prefs.maxTime} onChange={e=>setPrefs(p=>({...p,maxTime:+e.target.value}))}>
                  <option value={15}>15 min</option><option value={30}>30 min</option><option value={45}>45 min</option><option value={60}>60 min</option>
                </select>
                <button className="primary-btn" onClick={generateMealPlan} disabled={generatingPlan} style={{ marginTop:"22px", width:"100%", padding:"12px", borderRadius:"8px", border:"none", background: generatingPlan?"#1a3a1a":"#2a6a2a", color:"#c0e0c0", cursor: generatingPlan?"not-allowed":"pointer", fontSize:"13px", fontWeight:"600", letterSpacing:"0.5px" }}>
                  {generatingPlan ? "⏳ Generating AI plan..." : "✨ Generate AI Meal Plan"}
                </button>
              </div>

              <div style={T.card}>
                <div style={T.ct}>🔗 Scrape Recipe (RAG)</div>
                <input style={T.inp} value={scrapeUrl} onChange={e => setScrapeUrl(e.target.value)} placeholder="Paste recipe URL (e.g. from AllRecipes)" />
                <button className="check-btn" onClick={handleScrape} disabled={loading || !scrapeUrl} style={{ marginTop:"10px", width:"100%", padding:"9px", borderRadius:"7px", border:"1px solid #263826", background:"transparent", color:"#6a8a6a", cursor:"pointer", fontSize:"12px" }}>{loading ? "Scraping..." : "📥 Scrape & Embed"}</button>
              </div>
            </div>

            <div>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"18px" }}>
                <div>
                  <div style={{ fontSize:"20px", color:"#b8d0b8", fontWeight:"600" }}>Weekly Meal Plan</div>
                  <div style={{ fontSize:"12px", color:"#3a5a3a", marginTop:"2px" }}>{meals.length > 0 ? `${meals.length} meals · ~${Math.round(totalCal/7)} cal/day avg` : "Set preferences and generate a plan, or click + to add meals"}</div>
                </div>
                {meals.length > 0 && <button className="check-btn" onClick={()=>{setMealPlan({});setGroceryList([]);}} style={{ padding:"7px 16px", borderRadius:"7px", border:"1px solid #263826", background:"transparent", color:"#6a8a6a", cursor:"pointer", fontSize:"12px" }}>Clear Plan</button>}
              </div>

              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"separate", borderSpacing:"5px" }}>
                  <thead>
                    <tr>
                      <th style={{ width:"65px", fontSize:"9px", color:"#3a5a3a", letterSpacing:"1.5px", textAlign:"left", paddingBottom:"8px", paddingLeft:"4px" }}>MEAL</th>
                      {DAYS.map(d=><th key={d} style={{ fontSize:"9px", color:"#4a7a4a", letterSpacing:"1px", textAlign:"center", paddingBottom:"8px" }}>{d.slice(0,3).toUpperCase()}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {MEAL_TYPES.map(meal=>(
                      <tr key={meal}>
                        <td style={{ fontSize:"9px", color:"#3a5a3a", verticalAlign:"top", paddingTop:"10px", paddingRight:"4px", textAlign:"center" }}>
                          {meal==="Breakfast"?"🌅":meal==="Lunch"?"☀️":"🌙"}<br/>{meal.slice(0,5)}
                        </td>
                        {DAYS.map(day=>{
                          const recipe = mealPlan[day]?.[meal];
                          return <td key={day} style={{ verticalAlign:"top" }}><MealCellComp recipe={recipe} onAssign={r=>assignMeal(day,meal,r)} T={T} RECIPE_DB={RECIPE_DB} /></td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === "grocery" && (
          <div>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:"24px" }}>
              <div>
                <div style={{ fontSize:"20px", color:"#b8d0b8", fontWeight:"600" }}>🛒 Grocery List</div>
                <div style={{ fontSize:"12px", color:"#3a5a3a", marginTop:"2px" }}>{groceryList.length>0?`${groceryList.filter(i=>!i.checked).length} of ${groceryList.length} items remaining`:"Generate a meal plan first"}</div>
              </div>
            </div>

            {groceryList.length === 0 ? (
              <div style={{ ...T.card, textAlign:"center", padding:"60px" }}>
                <div style={{ fontSize:"44px", marginBottom:"14px" }}>🥬</div>
                <div style={{ fontSize:"15px", color:"#4a6a4a" }}>No grocery list yet</div>
                <button className="primary-btn" onClick={()=>setTab("planner")} style={{ marginTop:"18px", padding:"10px 22px", borderRadius:"7px", border:"none", background:"#2a6a2a", color:"#c0e0c0", cursor:"pointer", fontSize:"13px" }}>Go to Planner →</button>
              </div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"18px" }}>
                {groceryList.map((item, idx) => (
                  <div key={idx} style={{ ...T.card, padding:"12px 18px" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:"10px", opacity:item.checked?0.4:1 }}>
                      <input type="checkbox" checked={item.checked} onChange={()=>setGroceryList(gl=>gl.map((g,i)=>i===idx?{...g,checked:!g.checked}:g))} style={{ width:"16px", height:"16px", accentColor:"#6ec86e", cursor:"pointer" }} />
                      <div style={{ flex:1, fontSize:"14px", color:item.checked?"#3a5a3a":"#b8d0b8", textDecoration:item.checked?"line-through":"none", fontWeight:"600" }}>{item.item}</div>
                      <div style={{ fontSize:"12px", color:"#3a5a3a" }}>{Math.round(item.qty*10)/10} {item.unit}</div>
                    </div>
                    
                    <div style={{ marginTop: "12px", display:"flex", gap:"8px", opacity:item.checked?0.4:1 }}>
                       {item.instacart_url && (
                          <a href={item.instacart_url} target="_blank" rel="noreferrer" style={{ textDecoration:"none", fontSize:"11px", background:"#0d1a0d", padding:"4px 8px", borderRadius:"4px", color:"#6ec86e", border:"1px solid #1a2e1a" }}>🛒 Instacart</a>
                       )}
                       {item.amazon_url && (
                          <a href={item.amazon_url} target="_blank" rel="noreferrer" style={{ textDecoration:"none", fontSize:"11px", background:"#0d1a0d", padding:"4px 8px", borderRadius:"4px", color:"#e8b060", border:"1px solid #1a2e1a" }}>📦 Amazon Fresh</a>
                       )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "assistant" && (
          <div style={{ display:"grid", gridTemplateColumns:"1fr", gap:"20px" }}>
            <div style={{ ...T.card, display:"flex", flexDirection:"column", height:"640px" }}>
              <div style={{ ...T.ct, marginBottom:"14px" }}>🤖 AI Meal Assistant</div>
              <div ref={chatRef} style={{ flex:1, overflowY:"auto", display:"flex", flexDirection:"column", gap:"10px", paddingBottom:"8px" }}>
                {chat.map((msg,i)=>(
                  <div key={i} style={{ display:"flex", justifyContent: msg.role==="user"?"flex-end":"flex-start" }}>
                    <div style={T.cb(msg.role)}>{msg.content}</div>
                  </div>
                ))}
                {loading && <div style={{ display:"flex" }}><div style={{ ...T.cb("assistant"), color:"#3a5a3a" }}>⏳ thinking...</div></div>}
              </div>
              <div style={{ display:"flex", gap:"8px", marginTop:"10px" }}>
                <input style={{ ...T.inp, flex:1 }} value={chatInput} onChange={e=>setChatInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&sendChat()} placeholder="Ask about meals, nutrition, substitutions..." disabled={loading} />
                <button className="primary-btn" onClick={sendChat} disabled={loading||!chatInput.trim()} style={{ padding:"9px 18px", borderRadius:"7px", border:"none", background: loading||!chatInput.trim()?"#1a3a1a":"#2a6a2a", color:"#c0e0c0", cursor: loading||!chatInput.trim()?"not-allowed":"pointer", fontSize:"13px", fontWeight:"600" }}>Send</button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

function MealCellComp({ recipe, onAssign, T, RECIPE_DB }) {
  const [open, setOpen] = useState(false);
  if (recipe) {
    return (
      <div style={T.mc(true)}>
        <div style={{ fontSize:"12px", color:"#b8d0b8", fontWeight:"600", lineHeight:"1.3", paddingRight:"16px" }}>{recipe.name}</div>
        <div style={{ fontSize:"10px", color:"#3a5a3a", marginTop:"4px" }}>{recipe.time}min</div>
        <div style={{ fontSize:"10px", color:"#4a6a4a", marginTop:"3px" }}>{recipe.cuisine}</div>
        <button onClick={()=>onAssign(null)} style={{ position:"absolute", top:"5px", right:"6px", background:"none", border:"none", color:"#2a4a2a", cursor:"pointer", fontSize:"15px", lineHeight:1, padding:0 }}>×</button>
      </div>
    );
  }
  return (
    <div style={{ position:"relative" }}>
      <div className="meal-cell-empty" style={T.mc(false)} onClick={()=>setOpen(!open)}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:"50px", color:"#1e361e", fontSize:"20px" }}>+</div>
      </div>
      {open && (
        <div style={{ position:"absolute", top:"100%", left:0, zIndex:100, background:"#0f180f", border:"1px solid #263826", borderRadius:"9px", padding:"7px", minWidth:"160px", boxShadow:"0 8px 28px rgba(0,0,0,0.7)", maxHeight:"220px", overflowY:"auto" }}>
          {RECIPE_DB.map(r=>(
            <div key={r.id} className="recipe-option" onClick={()=>{onAssign(r);setOpen(false);}} style={{ padding:"7px 11px", cursor:"pointer", borderRadius:"5px", fontSize:"12px", color:"#b8d0b8", transition:"background 0.1s" }}>
              {r.name} <span style={{ fontSize:"10px", color:"#3a5a3a" }}>({r.time}m)</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
