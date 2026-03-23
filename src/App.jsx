import React, { useState, useEffect } from 'react';

const BACKEND_URL = "http://127.0.0.1:8000";

const css = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  body { font-family: 'Inter', sans-serif; margin: 0; background: #080d08; color: #e0d8c8; }
  .app-container { display: flex; flex-direction: column; min-height: 100vh; }
  
  /* Auth */
  .auth-container { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .auth-box { background: #0f180f; padding: 48px; border-radius: 24px; border: 1px solid #1c301c; width: 100%; max-width: 400px; text-align: center; }
  .auth-input { width: 100%; padding: 12px; margin-bottom: 16px; background: #080d08; border: 1px solid #1c301c; border-radius: 8px; color: white; box-sizing: border-box; outline: none; }
  .auth-btn { width: 100%; background: #2a6a2a; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: 700; cursor: pointer; transition: 0.2s; }
  .auth-switch { margin-top: 16px; color: #6ec86e; cursor: pointer; font-size: 14px; }

  /* Nav */
  .nav { border-bottom: 1px solid #1c301c; padding: 24px; display: flex; justify-content: space-between; align-items: center; background: rgba(8, 13, 8, 0.8); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 50; }
  .logo-container { display: flex; items-center; gap: 12px; }
  .logo-icon { width: 40px; height: 40px; background: #2a6a2a; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 24px; }
  .logo-text h1 { font-size: 24px; font-weight: 700; color: #6ec86e; margin: 0; }
  
  .tab-bar { display: flex; gap: 8px; background: #0f180f; padding: 4px; border-radius: 12px; border: 1px solid #1c301c; }
  .tab-btn { padding: 8px 20px; border-radius: 8px; border: none; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; color: #4a7a4a; background: transparent; }
  .tab-btn.active { background: #2a6a2a; color: white; }
  .logout-btn { background: transparent; color: #c86e6e; border: 1px solid #c86e6e; padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-left: 16px; font-size: 12px;}

  /* Main */
  .main { max-width: 1200px; margin: 0 auto; padding: 24px; width: 100%; box-sizing: border-box; }
  
  /* Chat */
  .chat-box { background: #0f180f; border: 1px solid #1c301c; border-radius: 24px; height: 700px; display: flex; flex-direction: column; overflow: hidden; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 32px; display: flex; flex-direction: column; gap: 24px; }
  .bubble { max-width: 85%; padding: 20px; border-radius: 24px; font-size: 15px; line-height: 1.6; }
  .user .bubble { background: #2a6a2a; color: white; align-self: flex-end; }
  .assistant .bubble { background: #1c301c; color: #e0d8c8; align-self: flex-start; }
  
  /* Planner Grid */
  .planner-grid { display: grid; grid-template-columns: 80px repeat(7, 1fr); gap: 12px; margin-top: 24px; overflow-x: auto; padding-bottom: 24px; }
  .grid-header { font-weight: 700; color: #6ec86e; text-align: center; padding: 12px; background: #0f180f; border-radius: 12px; border: 1px solid #1c301c; }
  .grid-time { font-weight: 600; color: #4a7a4a; display: flex; align-items: center; justify-content: center; font-size: 12px; }
  .grid-cell { background: #0f180f; border: 1px dashed #1c301c; border-radius: 16px; min-height: 120px; padding: 8px; cursor: pointer; display: flex; flex-direction: column; gap: 4px; transition: 0.2s; position: relative; }
  .grid-cell:hover { border-color: #2a6a2a; background: #1c301c; }
  .grid-cell.filled { border-style: solid; border-color: #2a6a2a; background: rgba(42, 106, 42, 0.1); }
  .cell-recipe-name { font-size: 11px; font-weight: 700; color: #6ec86e; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .cell-recipe-img { width: 100%; height: 60px; object-fit: cover; border-radius: 8px; margin-top: 4px; }

  /* Apply Plan Button */
  .apply-plan-btn { background: #6ec86e; color: #080d08; border: none; padding: 12px 24px; border-radius: 12px; font-weight: 700; cursor: pointer; margin-top: 16px; display: flex; align-items: center; gap: 8px; }
  
  /* Grid */
  .recipe-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; margin-top: 24px; }
  .recipe-card { background: #080d08; border-radius: 16px; border: 1px solid #1c301c; overflow: hidden; cursor: pointer; transition: 0.2s; }
  .recipe-card:hover { border-color: #6ec86e; }
  .card-img { width: 100%; height: 120px; object-fit: cover; }
  .modal-img { width: 100%; height: 300px; object-fit: cover; border-radius: 16px; margin-bottom: 24px; border: 1px solid #1c301c; }
  .card-body { padding: 12px; }
  .card-title { font-size: 14px; font-weight: 700; color: #6ec86e; margin: 0 0 4px; }
  .card-meta { font-size: 11px; color: #4a7a4a; }

  /* Input */
  .chat-input-area { padding: 24px; border-top: 1px solid #1c301c; display: flex; gap: 12px; }
  .chat-input { flex: 1; background: #080d08; border: 1px solid #1c301c; border-radius: 12px; padding: 12px 16px; color: white; outline: none; }
  .send-btn { background: #2a6a2a; color: white; border: none; padding: 12px 24px; border-radius: 12px; font-weight: 700; cursor: pointer; }

  /* Modal */
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.9); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 24px; }
  .modal { background: #0f180f; border: 1px solid #1c301c; border-radius: 32px; width: 100%; max-width: 800px; max-height: 90vh; overflow-y: auto; position: relative; }
  .modal-content { padding: 40px; }
  .close-modal { position: absolute; top: 24px; right: 24px; background: none; border: none; color: white; font-size: 24px; cursor: pointer; }
  
  .fav-btn { padding: 10px 20px; border-radius: 12px; font-weight: 700; cursor: pointer; border: none; margin-top: 16px; transition: 0.2s; }
  .fav-btn.add { background: #6ec86e; color: #080d08; }
  .fav-btn.remove { background: #c86e6e; color: white; }

  .calendar-btn { background: #4285F4; color: white; border: none; padding: 10px 20px; border-radius: 12px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: 0.2s; }
  .calendar-btn:hover { background: #357ae8; }
`;

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MEALS = ["Breakfast", "Lunch", "Dinner"];

const getWeekID = (date = new Date()) => {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${weekNo.toString().padStart(2, '0')}`;
};

export default function App() {
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const [activeTab, setActiveTab] = useState('chat');
  const [chatHistory, setChatHistory] = useState([
    { role: 'assistant', content: "Hello! I'm NourishAI, your personal healthy eating companion. How can I help you with your meal planning today?" }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [numRecipes, setNumRecipes] = useState(3);
  const [loading, setLoading] = useState(false);
  
  const [favorites, setFavorites] = useState([]);
  const [weeklySchedule, setWeeklySchedule] = useState({});
  const [recommendations, setRecommendations] = useState([]);
  const [allFetchedRecipes, setAllFetchedRecipes] = useState({}); 
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [currentWeek, setCurrentWeek] = useState(new Date());
  const [isSelectingFor, setIsSelectingFor] = useState(null);
  const [isGoogleConnected, setIsGoogleConnected] = useState(false);
  const [plannerPromptInput, setPlannerPromptInput] = useState('');
  const [isRecurringApplied, setIsRecurringApplied] = useState(false);

  const weekId = getWeekID(currentWeek);

  useEffect(() => {
    if (user) {
      fetchFavorites();
      checkGoogleStatus();
    }
  }, [user]);

  useEffect(() => {
    if (user && activeTab === 'planner') {
      fetchSchedule();
      fetchRecommendations();
    }
  }, [user, activeTab, weekId]);

  const handleAuth = async () => {
    if (!username || !password) return alert("Fill in all fields");
    const endpoint = authMode === 'login' ? '/api/auth/login' : '/api/auth/signup';
    try {
      const res = await fetch(`${BACKEND_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (res.ok) {
        setUser(data);
      } else alert(data.detail || "Auth failed");
    } catch { alert("Backend offline."); }
  };

  const checkGoogleStatus = async () => {
    if (!user) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/google/status/${user.user_id}`);
      const data = await res.json();
      setIsGoogleConnected(data.connected);
    } catch {}
  };

  const connectGoogle = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/auth/google/login/${user.user_id}`);
      const data = await res.json();
      // Use the URL from the backend exactly as provided
      window.open(data.url, 'GoogleLogin', 'width=600,height=600');
      
      // Poll for success
      const interval = setInterval(async () => {
        const check = await fetch(`${BACKEND_URL}/api/google/status/${user.user_id}`);
        const status = await check.json();
        if (status.connected) {
          setIsGoogleConnected(true);
          clearInterval(interval);
          alert("Google Calendar connected!");
        }
      }, 2000);
    } catch { alert("Failed to start Google login."); }
  };

  const exportToGoogle = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/google/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id, week_id: weekId, schedule: weeklySchedule })
      });
      const data = await res.json();
      if (res.ok) alert(`Success! Created ${data.events_created} events in your calendar.`);
      else alert("Export failed: " + data.detail);
    } catch { alert("Error connecting to Google."); }
    finally { setLoading(false); }
  };

  const fetchFavorites = async () => {
    if (!user) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/favorites/${user.user_id}`);
      const data = await res.json();
      const favs = data.recipes || [];
      setFavorites(favs);
      setAllFetchedRecipes(prev => {
        const next = { ...prev };
        favs.forEach(r => next[r.id] = r);
        return next;
      });
    } catch {}
  };

  const fetchSchedule = async () => {
    if (!user) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/schedule/${user.user_id}/${weekId}`);
      const data = await res.json();
      setWeeklySchedule(data.schedule || {});
      setIsRecurringApplied(data.is_recurring_applied || false);
      if (data.recipes) {
        setAllFetchedRecipes(prev => ({ ...prev, ...data.recipes }));
      }
    } catch {
      setWeeklySchedule({});
    }
  };

  const handlePlannerPrompt = async () => {
    if (!plannerPromptInput.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/planner/prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: plannerPromptInput })
      });
      const data = await res.json();
      if (data.suggested_plan) {
        setWeeklySchedule(data.suggested_plan);
        if (data.recipes) {
          setAllFetchedRecipes(prev => {
            const next = { ...prev };
            data.recipes.forEach(r => next[r.id] = r);
            return next;
          });
        }
        setPlannerPromptInput('');
      } else alert("AI couldn't generate a plan. Try a different prompt.");
    } catch { alert("Error generating plan."); }
    finally { setLoading(false); }
  };

  const autoFillPlanner = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/planner/autofill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id })
      });
      const data = await res.json();
      setWeeklySchedule(data.schedule);
      if (data.recipes) {
        setAllFetchedRecipes(prev => ({ ...prev, ...data.recipes }));
      }
    } catch { alert("Error auto-filling."); }
    finally { setLoading(false); }
  };

  const setAsRecurring = async () => {
    if (!confirm("Save this current week as your recurring template? It will show up for any empty future weeks.")) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id, week_id: 'recurring', schedule: weeklySchedule })
      });
      if (res.ok) alert("Default recurring schedule saved!");
    } catch { alert("Error saving recurring schedule."); }
  };

  const fetchRecommendations = async () => {
    if (!user) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/recommendations/${user.user_id}`);
      const data = await res.json();
      setRecommendations(data.recipes || []);
      setAllFetchedRecipes(prev => {
        const next = { ...prev };
        (data.recipes || []).forEach(r => next[r.id] = r);
        return next;
      });
    } catch {}
  };

  const handleChat = async () => {
    if (!chatInput.trim()) return;
    const msg = chatInput;
    setChatInput('');
    setChatHistory(prev => [...prev, { role: 'user', content: msg }]);
    setLoading(true);

    try {
      const res = await fetch(`${BACKEND_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: msg, 
          history: chatHistory.slice(-5),
          num_recipes: parseInt(numRecipes)
        })
      });
      const data = await res.json();
      
      setAllFetchedRecipes(prev => {
        const next = { ...prev };
        (data.recipes || []).forEach(r => next[r.id] = r);
        return next;
      });

      setChatHistory(prev => [...prev, { 
        role: 'assistant', 
        content: data.message, 
        recipes: data.recipes,
        suggested_plan: data.suggested_plan
      }]);
    } catch {
      setChatHistory(prev => [...prev, { role: 'assistant', content: "Error connecting to backend." }]);
    } finally {
      setLoading(false);
    }
  };

  const applyPlan = async (plan) => {
    setWeeklySchedule(plan);
    try {
      const res = await fetch(`${BACKEND_URL}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id, week_id: weekId, schedule: plan })
      });
      if (res.ok) {
        alert("Plan applied to your weekly schedule!");
        setActiveTab('planner');
      }
    } catch { alert("Failed to save schedule."); }
  };

  const saveManualSchedule = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id, week_id: weekId, schedule: weeklySchedule })
      });
      if (res.ok) alert("Schedule saved!");
    } catch { alert("Error saving schedule."); }
  };

  const addToPlanner = (recipe) => {
    if (!isSelectingFor) return;
    const { day, meal } = isSelectingFor;
    setWeeklySchedule(prev => ({
      ...prev,
      [day]: {
        ...(prev[day] || { Breakfast: null, Lunch: null, Dinner: null }),
        [meal]: recipe.id
      }
    }));
    setAllFetchedRecipes(prev => ({ ...prev, [recipe.id]: recipe }));
    setIsSelectingFor(null);
    setSelectedRecipe(null);
  };

  const changeWeek = (offset) => {
    const next = new Date(currentWeek);
    next.setDate(next.getDate() + offset * 7);
    setCurrentWeek(next);
  };

  const toggleFavorite = async (recipe) => {
    if (!recipe || !recipe.id) return;
    const isCurrentlyFav = favorites.some(f => f.id === recipe.id);
    const path = isCurrentlyFav ? 'api/favorites/remove' : 'api/favorites';
    const body = isCurrentlyFav ? { user_id: user.user_id, recipe_id: recipe.id } : { user_id: user.user_id, recipe };

    try {
      const res = await fetch(`${BACKEND_URL}/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (res.ok) {
        await fetchFavorites();
        alert(isCurrentlyFav ? "Removed!" : "Added!");
      }
    } catch (err) { alert("Network error."); }
  };

  const isFav = (rid) => favorites.some(f => f.id === rid);

  const getWeekRange = () => {
    const start = new Date(currentWeek);
    start.setDate(start.getDate() - start.getDay());
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    const options = { month: 'short', day: 'numeric' };
    return `${start.toLocaleDateString(undefined, options)} - ${end.toLocaleDateString(undefined, options)}, ${end.getFullYear()}`;
  };

  if (!user) return (
    <div className="auth-container">
      <style>{css}</style>
      <div className="auth-box">
        <div className="logo-icon" style={{margin:'0 auto 24px'}}>🌿</div>
        <h2>{authMode === 'login' ? 'Login to NourishAI' : 'Create Account'}</h2>
        <input className="auth-input" placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} />
        <input className="auth-input" type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} />
        <button className="auth-btn" onClick={handleAuth}>{authMode === 'login' ? 'Login' : 'Signup'}</button>
        <p className="auth-switch" onClick={() => setAuthMode(authMode === 'login' ? 'signup' : 'login')}>
          {authMode === 'login' ? "New? Sign up" : "Back to Login"}
        </p>
      </div>
    </div>
  );

  return (
    <div className="app-container">
      <style>{css}</style>
      <nav className="nav">
        <div className="logo-container">
          <div className="logo-icon">🌿</div>
          <div className="logo-text">
            <h1>NourishAI</h1>
            <div style={{ fontSize: '10px', color: '#4a7a4a', fontWeight: 'bold' }}>CHEF {user.username}</div>
          </div>
        </div>
        <div style={{display:'flex', gap:'12px', alignItems:'center'}}>
          {!isGoogleConnected ? (
            <button className="calendar-btn" onClick={connectGoogle}>Connect Google Calendar</button>
          ) : (
            <span style={{color:'#6ec86e', fontSize:'12px', fontWeight:'700'}}>✓ Calendar Connected</span>
          )}
          <div className="tab-bar">
            {['chat', 'planner', 'favorites'].map(t => (
              <button key={t} onClick={() => setActiveTab(t)} className={`tab-btn ${activeTab === t ? 'active' : ''}`}>
                {t.toUpperCase()}
              </button>
            ))}
          </div>
          <button className="logout-btn" onClick={() => setUser(null)}>LOGOUT</button>
        </div>
      </nav>

      <main className="main">
        {activeTab === 'chat' && (
          <div className="chat-box">
            <div className="chat-messages">
              {chatHistory.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'user' : 'assistant'} style={{display:'flex', flexDirection:'column'}}>
                  <div className="bubble">
                    {m.content}
                    {m.suggested_plan && (
                      <button className="apply-plan-btn" onClick={() => applyPlan(m.suggested_plan)}>
                        📅 Apply this Weekly Plan to my Schedule
                      </button>
                    )}
                  </div>
                  {m.recipes && (
                    <div className="recipe-grid">
                      {m.recipes.map(r => (
                        <div key={r.id} className="recipe-card" onClick={() => isSelectingFor ? addToPlanner(r) : setSelectedRecipe(r)}>
                          <img 
                            src={r.image || 'https://placehold.co/250x120?text=No+Image'} 
                            className="card-img" 
                            onError={(e) => { e.target.src = 'https://placehold.co/250x120?text=Error'; }}
                          />
                          <div className="card-body">
                            <p className="card-title">{r.name}</p>
                            <div className="card-meta"><span>{r.cuisine}</span></div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {loading && <div className="assistant"><div className="bubble">...</div></div>}
            </div>
            <div className="chat-input-area">
              <input className="chat-input" placeholder="Ask for a recipe or plan..." value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyPress={e => e.key === 'Enter' && handleChat()} />
              <button className="send-btn" onClick={handleChat}>Send</button>
            </div>
          </div>
        )}

        {activeTab === 'planner' && (
          <div>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px'}}>
              <div>
                <h2 style={{color:'#6ec86e', margin:0}}>Weekly Meal Schedule</h2>
                <p style={{color:'#4a7a4a', fontSize:'14px', fontWeight:'700', marginTop:'4px'}}>
                  {getWeekRange()} 
                  {isRecurringApplied && <span style={{marginLeft:'12px', background:'#2a6a2a', color:'white', padding:'2px 8px', borderRadius:'4px', fontSize:'10px'}}>RECURRING APPLIED</span>}
                </p>
              </div>
              <div style={{display:'flex', gap:'12px', alignItems:'center'}}>
                {isGoogleConnected && <button className="calendar-btn" onClick={exportToGoogle}>📅 Export to Calendar</button>}
                <button className="tab-btn" onClick={() => changeWeek(-1)}>← Previous</button>
                <button className="tab-btn" onClick={() => changeWeek(1)}>Next →</button>
                <button className="apply-plan-btn" style={{marginTop:0}} onClick={saveManualSchedule}>💾 Save Changes</button>
              </div>
            </div>

            <div style={{background: '#0f180f', padding: '16px', borderRadius: '16px', border: '1px solid #1c301c', marginBottom: '24px', display:'flex', gap: '12px', alignItems: 'center'}}>
              <input 
                className="chat-input" 
                placeholder="Ask AI to arrange your week (e.g. 'high protein', 'vegan Mon-Wed')..." 
                value={plannerPromptInput} 
                onChange={e => setPlannerPromptInput(e.target.value)}
                onKeyPress={e => e.key === 'Enter' && handlePlannerPrompt()}
              />
              <button className="send-btn" onClick={handlePlannerPrompt} disabled={loading}>{loading ? '...' : 'Generate'}</button>
              <div style={{width:'1px', height:'30px', background:'#1c301c'}}></div>
              <button className="tab-btn" onClick={autoFillPlanner} style={{borderColor:'#6ec86e', color:'#6ec86e'}}>🪄 Auto-Fill</button>
              <button className="tab-btn" onClick={setAsRecurring} style={{borderColor:'#4285F4', color:'#4285F4'}}>🔁 Set Recurring</button>
            </div>

            <div className="planner-grid">
              <div className="grid-header" style={{background:'transparent', border:'none'}}></div>
              {DAYS.map(d => <div key={d} className="grid-header">{d}</div>)}
              {MEALS.map(m => (
                <React.Fragment key={m}>
                  <div className="grid-time">{m}</div>
                  {DAYS.map(d => {
                    const recipeId = weeklySchedule?.[d]?.[m];
                    const recipe = allFetchedRecipes[recipeId];
                    return (
                      <div key={d+m} className={`grid-cell ${recipe ? 'filled' : ''}`} onClick={() => { if (recipe) setSelectedRecipe(recipe); else setIsSelectingFor({ day: d, meal: m }); }}>
                        {recipe ? (
                          <>
                            <span className="cell-recipe-name">{recipe.name}</span>
                            {recipe.image && (
                              <img 
                                src={recipe.image} 
                                className="cell-recipe-img" 
                                onError={(e) => { e.target.src = 'https://placehold.co/100x60?text=Error'; }} 
                              />
                            )}
                            <button style={{position:'absolute', top:4, right:4, background:'rgba(200,110,110,0.8)', color:'white', border:'none', borderRadius:'50%', width:'16px', height:'16px', fontSize:'10px', cursor:'pointer'}} onClick={(e) => { e.stopPropagation(); setWeeklySchedule(prev => ({ ...prev, [d]: { ...(prev?.[d] || {}), [m]: null } })); }}>✕</button>
                          </>
                        ) : <span style={{fontSize:'10px', color:'#4a7a4a'}}>+ Add</span>}
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>

            <div style={{marginTop:'40px'}}>
              <h3 style={{color:'#6ec86e'}}>Suggestions for you</h3>
              <div className="recipe-grid">
                {recommendations.map(r => (
                  <div key={r.id} className="recipe-card" onClick={() => isSelectingFor ? addToPlanner(r) : setSelectedRecipe(r)}>
                    <img 
                      src={r.image || 'https://placehold.co/250x120?text=No+Image'} 
                      className="card-img" 
                      onError={(e) => { e.target.src = 'https://placehold.co/250x120?text=Error'; }}
                    />
                    <div className="card-body"><p className="card-title">{r.name}</p></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'favorites' && (
          <div>
            <h2 style={{color:'#6ec86e'}}>Saved Favorites</h2>
            <div className="recipe-grid">
              {favorites.map(r => (
                <div key={r.id} className="recipe-card" onClick={() => isSelectingFor ? addToPlanner(r) : setSelectedRecipe(r)}>
                  <img 
                    src={r.image || 'https://placehold.co/250x120?text=No+Image'} 
                    className="card-img" 
                    onError={(e) => { e.target.src = 'https://placehold.co/250x120?text=Error'; }}
                  />
                  <div className="card-body"><p className="card-title">{r.name}</p></div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {selectedRecipe && (
        <div className="modal-overlay" onClick={() => setSelectedRecipe(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <button className="close-modal" onClick={() => setSelectedRecipe(null)}>✕</button>
            <div className="modal-content">
              {selectedRecipe.image && (
                <img 
                  src={selectedRecipe.image} 
                  className="modal-img" 
                  alt={selectedRecipe.name} 
                  onError={(e) => { e.target.src = 'https://placehold.co/600x300?text=Error+Loading+Image'; }}
                />
              )}
              <h2 style={{color:'#6ec86e', marginTop: selectedRecipe.image ? '0' : '24px'}}>{selectedRecipe.name}</h2>
              <p style={{color:'#4a7a4a'}}>{selectedRecipe.cuisine} • {selectedRecipe.category}</p>
              <button className={`fav-btn ${isFav(selectedRecipe.id) ? 'remove' : 'add'}`} onClick={() => toggleFavorite(selectedRecipe)}>
                {isFav(selectedRecipe.id) ? '✕ Remove' : '❤ Favorite'}
              </button>
              <div style={{marginTop:'24px', display:'grid', gridTemplateColumns:'1fr 2fr', gap:'32px'}}>
                <div><h3>Ingredients</h3><ul>{(selectedRecipe.ingredients || []).map((ing, i) => <li key={i}>{ing.item || ing}</li>)}</ul></div>
                <div><h3>Instructions</h3><p style={{whiteSpace:'pre-wrap'}}>{selectedRecipe.instructions}</p></div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
