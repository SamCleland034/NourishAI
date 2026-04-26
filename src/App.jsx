import React, { useState, useEffect } from 'react';

const BACKEND_URL = import.meta.env.VITE_API_URL || ""; // Proxy handles this in dev

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
  .grocery-list { list-style: none; padding: 0; margin: 0; }
  .grocery-item { display: flex; align-items: center; gap: 16px; padding: 12px 0; border-bottom: 1px solid #1c301c; }
  .grocery-item:last-child { border-bottom: none; }
  .grocery-item span { font-size: 16px; color: #e0d8c8; }
  .prep-table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 16px; border: 1px solid #1c301c; border-radius: 12px; overflow: hidden; }
  .prep-table th { background: #1c301c; color: #6ec86e; text-align: left; padding: 16px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
  .prep-table td { padding: 16px; border-bottom: 1px solid #1c301c; font-size: 14px; vertical-align: top; }
  .prep-table tr:last-child td { border-bottom: none; }
  .step-col { width: 60px; font-weight: 700; color: #6ec86e; text-align: center; }
  .meal-col { width: 150px; font-weight: 600; color: #4a7a4a; font-size: 12px; }
  .task-col { color: #e0d8c8; line-height: 1.5; }
  .tip-col { font-style: italic; color: #6ec86e; font-size: 12px; background: rgba(110, 200, 110, 0.05); }

  /* Nutrition */
  .nutrition-summary { margin-top: 12px; padding: 12px; background: #1c301c; border-radius: 12px; font-size: 11px; color: #e0d8c8; }
  .nutrition-stat { display: flex; justify-content: space-between; margin-bottom: 4px; }
  .nutrition-label { color: #4a7a4a; font-weight: 600; }
  .nutrition-value { color: #6ec86e; font-weight: 700; }
  .weekly-summary-card { background: #0f180f; border: 1px solid #1c301c; border-radius: 24px; padding: 24px; margin-top: 32px; }

  /* Spinner */
  .spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(255,255,255,0.3);
    border-radius: 50%;
    border-top-color: #fff;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .btn-content { display: flex; align-items: center; justify-content: center; gap: 8px; }
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

  const [activeTab, setActiveTab] = useState('home');
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
  const [groceryList, setGroceryList] = useState({});
  const [unitSystem, setUnitSystem] = useState('imperial');
  const [isGroceryLoading, setIsGroceryLoading] = useState(false);
  const [showPrepModal, setShowPrepModal] = useState(false);
  const [prepGuide, setPrepGuide] = useState([]);
  const [prepGuideChecked, setPrepGuideChecked] = useState({}); // Added state
  const [isPrepLoading, setIsPrepLoading] = useState(false);
  const [dailyStats, setDailyStats] = useState({});
  const [weeklyStats, setWeeklyStats] = useState({});
  const [manualSearchQuery, setManualSearchQuery] = useState('');
  const [manualSearchResults, setManualSearchResults] = useState([]);
  const [isManualSearchLoading, setIsManualSearchLoading] = useState(false);
  const [isRefreshingRecs, setIsRefreshingRecs] = useState(false);
  const [modalServings, setModalServings] = useState(4);

  const weekId = getWeekID(currentWeek);

  const scaleQuantity = (qty, factor) => {
    if (!qty) return '';
    // Match numbers, fractions, or decimals at the start of the string
    // This regex handles "1", "1/2", "1.5", "1 1/2"
    const match = qty.match(/^(\d+\s+)?(\d+\/\d+|\d+(\.\d+)?)/);
    if (!match) return qty;

    const numStr = match[0];
    const rest = qty.slice(numStr.length);

    const parseValue = (s) => {
      s = s.trim();
      if (s.includes('/')) {
        const [n, d] = s.split('/').map(Number);
        return n / d;
      }
      return Number(s);
    };

    let value = 0;
    if (numStr.trim().includes(' ') && numStr.includes('/')) {
        const parts = numStr.trim().split(/\s+/);
        value = Number(parts[0]) + parseValue(parts[1]);
    } else {
        value = parseValue(numStr);
    }

    const scaledValue = value * factor;
    
    // Format back - if it's very close to an integer, show as integer
    const formatted = Number.isInteger(scaledValue * 4) ? 
      (scaledValue % 1 === 0 ? scaledValue : scaledValue.toFixed(2).replace(/\.?0+$/, '')) : 
      scaledValue.toFixed(2).replace(/\.?0+$/, '');

    return `${formatted}${rest}`;
  };

  useEffect(() => {
    if (user) {
      fetchFavorites();
      checkGoogleStatus();
    }
  }, [user]);

  useEffect(() => {
    if (user && (activeTab === 'planner' || activeTab === 'home')) {
      fetchSchedule();
    }
  }, [user, activeTab, weekId]);

  useEffect(() => {
    if (user && recommendations.length === 0) {
      fetchRecommendations();
    }
  }, [user]);

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
    } catch (e) { 
      console.error("Auth Error:", e);
      alert("Connectivity issue. Please ensure the backend is running at " + BACKEND_URL); 
    }
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
      console.log("DEBUG: Fetched Schedule Data:", data);
      setWeeklySchedule(data.schedule || {});
      setIsRecurringApplied(data.is_recurring_applied || false);
      setDailyStats(data.daily_stats || {});
      setWeeklyStats(data.weekly_stats || {});
      if (data.recipes) {
        setAllFetchedRecipes(prev => ({ ...prev, ...data.recipes }));
      }
    } catch {
      setWeeklySchedule({});
    }
  };

  const handleManualSearch = async () => {
    if (!manualSearchQuery.trim()) return;
    setIsManualSearchLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/recipes/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: manualSearchQuery, limit: 12 })
      });
      const data = await res.json();
      setManualSearchResults(data.recipes || []);
      if (data.recipes) {
        setAllFetchedRecipes(prev => {
          const next = { ...prev };
          data.recipes.forEach(r => { if (r && r.id) next[r.id] = r; });
          return next;
        });
      }
    } catch (e) {
      alert("Search failed: " + e.message);
    } finally {
      setIsManualSearchLoading(false);
    }
  };

  const fetchGroceryList = async () => {
    // Check if there are any recipes in the schedule
    const hasRecipes = Object.values(weeklySchedule).some(day => day && Object.values(day).some(rid => rid));
    if (!hasRecipes) {
      alert("Please add some recipes to your planner first!");
      return;
    }

    setIsGroceryLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/grocery-list`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          user_id: user.user_id, 
          week_id: weekId, 
          schedule: weeklySchedule,
          unit_system: unitSystem 
        })
      });
      const data = await res.json();
      setGroceryList(data.grocery_list || {});
    } catch { alert("Failed to fetch grocery list."); }
    finally { setIsGroceryLoading(false); }
  };

  const fetchPrepGuide = async () => {
    const hasRecipes = Object.values(weeklySchedule).some(day => day && Object.values(day).some(rid => rid));
    if (!hasRecipes) {
      alert("Please add some recipes to your planner first!");
      return;
    }

    setIsPrepLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/meal-prep-guide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id, week_id: weekId, schedule: weeklySchedule })
      });
      const data = await res.json();
      setPrepGuide(data.guide || []); // Ensure array
      setShowPrepModal(true);
    } catch { alert("Failed to fetch prep guide."); }
    finally { setIsPrepLoading(false); }
  };

  const handlePlannerPrompt = async () => {
    if (!plannerPromptInput.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/planner/prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: plannerPromptInput,
          exclude_ids: Object.keys(allFetchedRecipes),
          user_id: user.user_id,
          week_id: weekId,
          current_schedule: weeklySchedule // Send current state
        })
      });
      
      if (res.status === 429) {
        alert("AI Rate Limit Reached (Gemini). Please wait 60 seconds and try again.");
        return;
      }
      
      let data;
      const contentType = res.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        data = await res.json();
      } else {
        const text = await res.text();
        throw new Error(text || "Server returned non-JSON error");
      }

      if (!res.ok) throw new Error(data?.detail || "Server error");

      if (data.suggested_plan) {
        // AI now returns the MERGED plan from the backend
        setWeeklySchedule(data.suggested_plan);
        setDailyStats(data.daily_stats || {});
        setWeeklyStats(data.weekly_stats || {});
        if (data.recipes) {
          setAllFetchedRecipes(prev => {
            const next = { ...prev };
            data.recipes.forEach(r => { if(r && r.id) next[r.id] = r; });
            return next;
          });
        }
        setPlannerPromptInput('');
      } else {
        alert("AI couldn't generate a plan. Try a different prompt.");
      }
    } catch (e) {
      alert("Error generating plan: " + e.message);
      console.error("PLANNER ERROR:", e);
    } finally { setLoading(false); }
  };

  const autoFillPlanner = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/planner/autofill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id, week_id: weekId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Autofill failed");
      
      setWeeklySchedule(data.schedule || {});
      setDailyStats(data.daily_stats || {});
      setWeeklyStats(data.weekly_stats || {});
      if (data.recipes && Array.isArray(data.recipes)) {
        setAllFetchedRecipes(prev => {
          const next = { ...prev };
          data.recipes.forEach(r => { if (r && r.id) next[r.id] = r; });
          return next;
        });
      }
    } catch (e) { 
      alert("Auto-fill error: " + e.message);
      console.error("AUTOFILL ERROR:", e);
    }
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
    setIsRefreshingRecs(true);
    
    const fallbackRecs = [
      { id: 'mock-1', name: 'Mediterranean Quinoa Bowl', cuisine: 'Mediterranean', category: 'Lunch', image: 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=500&q=80', ingredients: [{item: 'Quinoa'}, {item:'Cherry Tomatoes'}, {item:'Cucumber'}, {item:'Feta Cheese'}], instructions: 'Mix all ingredients together with a light lemon dressing.' },
      { id: 'mock-2', name: 'Grilled Lemon Herb Chicken', cuisine: 'American', category: 'Dinner', image: 'https://images.unsplash.com/photo-1598514982205-f36b96d1e8d4?w=500&q=80', ingredients: [{item: 'Chicken Breast'}, {item:'Lemon'}, {item:'Herbs'}], instructions: 'Marinate chicken in lemon and herbs, then grill until cooked through.' },
      { id: 'mock-3', name: 'Avocado Berry Smoothie', cuisine: 'Healthy', category: 'Breakfast', image: 'https://images.unsplash.com/photo-1628557044797-f21a177c37ec?w=500&q=80', ingredients: [{item: 'Avocado'}, {item:'Mixed Berries'}, {item:'Almond Milk'}], instructions: 'Blend all ingredients until smooth.' }
    ];

    try {
      const res = await fetch(`${BACKEND_URL}/api/recommendations/${user.user_id}`);
      const data = await res.json();
      
      let recs = data.recipes || [];
      if (recs.length === 0) {
        recs = fallbackRecs;
      }

      setRecommendations(recs);
      setAllFetchedRecipes(prev => {
        const next = { ...prev };
        recs.forEach(r => next[r.id] = r);
        return next;
      });
    } catch {
      setRecommendations(fallbackRecs);
      setAllFetchedRecipes(prev => {
        const next = { ...prev };
        fallbackRecs.forEach(r => next[r.id] = r);
        return next;
      });
    } finally {
      setIsRefreshingRecs(false);
    }
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
          history: chatHistory.slice(-5).map(h => ({ role: h.role, content: h.content })),
          num_recipes: parseInt(numRecipes),
          exclude_ids: Object.keys(allFetchedRecipes),
          current_schedule: weeklySchedule // Pass for context
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
        suggested_plan: data.suggested_plan,
        daily_stats: data.daily_stats,
        weekly_stats: data.weekly_stats
      }]);
    } catch {
      setChatHistory(prev => [...prev, { role: 'assistant', content: "Error connecting to backend." }]);
    } finally {
      setLoading(false);
    }
  };

  const applyPlan = async (plan, dailyStats, weeklyStats) => {
    setWeeklySchedule(plan);
    if (dailyStats) setDailyStats(dailyStats);
    if (weeklyStats) setWeeklyStats(weeklyStats);
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
    if (!isSelectingFor) {
      console.log("addToPlanner called but isSelectingFor is null");
      return;
    }
    const { day, meal } = isSelectingFor;
    console.log(`Adding ${recipe.name} to ${day} ${meal}`);
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
    alert(`Added ${recipe.name} to your plan for ${day}! Remember to 'Save Changes' if you're done.`);
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
            {['home', 'planner', 'favorites'].map(t => (
              <button key={t} onClick={() => setActiveTab(t)} className={`tab-btn ${activeTab === t ? 'active' : ''}`}>
                {t.toUpperCase()}
              </button>
            ))}
          </div>
          <button className="logout-btn" onClick={() => setUser(null)}>LOGOUT</button>
        </div>
      </nav>

      <main className="main">
        {activeTab === 'home' && (
          <div style={{animation: 'fadeIn 0.5s ease-in', display: 'grid', gridTemplateColumns: '1fr 400px', gap: '32px'}}>
            <div className="home-dashboard">
              <div style={{marginBottom: '40px'}}>
                <h1 style={{color:'#6ec86e', fontSize: '36px', marginBottom: '8px', fontWeight: 800}}>Dashboard</h1>
                <p style={{color:'#4a7a4a', fontSize: '18px'}}>Your nutritional journey, consolidated.</p>
              </div>

              {/* Weekly Preview Section */}
              <section style={{marginBottom: '48px', background: 'rgba(110, 200, 110, 0.05)', padding: '24px', borderRadius: '24px', border: '1px solid #1c301c'}}>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px'}}>
                  <h2 style={{color:'#6ec86e', margin:0, fontSize: '20px', fontWeight: 700}}>Your Weekly Plan</h2>
                  <button className="tab-btn" onClick={() => setActiveTab('planner')} style={{fontSize: '12px'}}>Full Planner</button>
                </div>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '8px'}}>
                  {DAYS.map(day => (
                    <div key={day} style={{textAlign: 'center'}}>
                      <div style={{fontSize: '10px', color: '#4a7a4a', fontWeight: 'bold', marginBottom: '8px'}}>{day}</div>
                      <div style={{height: '40px', background: '#080d08', border: '1px solid #1c301c', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px'}}>
                        {weeklySchedule[day] && Object.values(weeklySchedule[day]).some(v => v) ? '🍽️' : '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section style={{marginBottom: '48px'}}>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px'}}>
                  <h2 style={{color:'#6ec86e', margin:0, fontSize: '20px', fontWeight: 700}}>Recommended for You</h2>
                </div>
                <div className="recipe-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))'}}>
                  {recommendations.length > 0 ? recommendations.map(r => (
                    <div key={r.id} className="recipe-card" onClick={() => setSelectedRecipe(r)}>
                      <img 
                        src={r.image || 'https://placehold.co/250x120?text=No+Image'} 
                        className="card-img" 
                        onError={(e) => { e.target.src = `https://placehold.co/250x120?text=${encodeURIComponent(r.name || r.title || 'Recipe')}`; }}
                      />
                      <div className="card-body">
                        <p className="card-title">{r.name}</p>
                        <div className="card-meta"><span>{r.cuisine} • {r.category}</span></div>
                      </div>
                    </div>
                  )) : <p style={{color:'#4a7a4a'}}>Favorite some recipes to get personalized recommendations!</p>}
                </div>
              </section>

              <section>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px', borderTop: '1px solid #1c301c', paddingTop: '32px'}}>
                  <h2 style={{color:'#6ec86e', margin:0, fontSize: '20px', fontWeight: 700}}>Your Favorites</h2>
                  <button className="tab-btn" onClick={() => setActiveTab('favorites')} style={{fontSize: '12px'}}>View All</button>
                </div>
                <div className="recipe-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))'}}>
                  {favorites.length > 0 ? favorites.slice(0, 4).map(r => (
                    <div key={r.id} className="recipe-card" onClick={() => setSelectedRecipe(r)}>
                      <img 
                        src={r.image || 'https://placehold.co/250x120?text=No+Image'} 
                        className="card-img" 
                        onError={(e) => { e.target.src = `https://placehold.co/250x120?text=${encodeURIComponent(r.name || r.title || 'Recipe')}`; }}
                      />
                      <div className="card-body">
                        <p className="card-title">{r.name}</p>
                        <div className="card-meta"><span>{r.cuisine} • {r.category}</span></div>
                      </div>
                    </div>
                  )) : <p style={{color:'#4a7a4a'}}>You haven't added any favorites yet.</p>}
                </div>
              </section>
            </div>

            <aside className="home-chat-sidebar">
              <div className="chat-box" style={{height: 'calc(100vh - 180px)', position: 'sticky', top: '100px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)'}}>
                <div style={{padding: '20px', borderBottom: '1px solid #1c301c', background: '#1c301c'}}>
                  <h3 style={{margin: 0, color: '#6ec86e', fontSize: '16px'}}>AI Assistant</h3>
                  <p style={{margin: 0, fontSize: '11px', color: '#4a7a4a'}}>Ask for plans or recipes</p>
                </div>
                <div className="chat-messages" style={{padding: '20px'}}>
                  {chatHistory.map((m, i) => (
                    <div key={i} className={m.role === 'user' ? 'user' : 'assistant'} style={{display:'flex', flexDirection:'column'}}>
                      <div className="bubble" style={{padding: '12px 16px', fontSize: '14px', borderRadius: '16px'}}>
                        {m.content}
                        {m.suggested_plan && (
                          <button className="apply-plan-btn" onClick={() => applyPlan(m.suggested_plan, m.daily_stats, m.weekly_stats)} style={{fontSize: '12px', padding: '8px 12px'}}>
                            📅 Apply Weekly Plan
                          </button>
                        )}
                      </div>
                      {m.recipes && (
                        <div className="recipe-grid" style={{gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px'}}>
                          {m.recipes.map(r => (
                            <div key={r.id} className="recipe-card" onClick={() => isSelectingFor ? addToPlanner(r) : setSelectedRecipe(r)} style={{borderRadius: '8px'}}>
                              <img 
                                src={r.image || 'https://placehold.co/100x60?text=No+Image'} 
                                className="card-img" 
                                style={{height: '60px'}}
                                onError={(e) => { e.target.src = 'https://placehold.co/100x60?text=Error'; }}
                              />
                              <div className="card-body" style={{padding: '6px'}}>
                                <p className="card-title" style={{fontSize: '11px'}}>{r.name}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                  {loading && <div className="assistant"><div className="bubble" style={{padding: '8px 16px', borderRadius: '16px'}}>...</div></div>}
                </div>
                <div className="chat-input-area" style={{padding: '16px'}}>
                  <input className="chat-input" style={{fontSize: '13px'}} placeholder="What's for dinner?" value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyPress={e => e.key === 'Enter' && handleChat()} />
                  <button className="send-btn" onClick={handleChat} style={{padding: '8px 16px', fontSize: '13px'}}>Ask</button>
                </div>
              </div>
            </aside>
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

            {isSelectingFor && (
              <div style={{background: '#1c301c', padding: '24px', borderRadius: '24px', border: '1px solid #6ec86e', marginBottom: '24px', animation: 'fadeIn 0.3s ease'}}>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: '16px'}}>
                  <h3 style={{margin:0, color:'#6ec86e'}}>Add Recipe to {isSelectingFor.day} {isSelectingFor.meal}</h3>
                  <button onClick={() => { setIsSelectingFor(null); setManualSearchResults([]); setManualSearchQuery(''); }} style={{background:'none', border:'none', color:'#4a7a4a', cursor:'pointer', fontSize: '18px'}}>✕</button>
                </div>
                <div style={{display:'flex', gap: '12px', marginBottom: '16px'}}>
                  <input 
                    className="chat-input" 
                    placeholder="Search recipes (e.g. 'salmon', 'pasta')..." 
                    value={manualSearchQuery}
                    onChange={e => setManualSearchQuery(e.target.value)}
                    onKeyPress={e => e.key === 'Enter' && handleManualSearch()}
                  />
                  <button className="send-btn" onClick={handleManualSearch} disabled={isManualSearchLoading}>
                    {isManualSearchLoading ? 'Searching...' : 'Search'}
                  </button>
                </div>
                {manualSearchResults.length > 0 ? (
                  <div className="recipe-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '12px'}}>
                    {manualSearchResults.map(r => (
                      <div key={r.id} className="recipe-card" onClick={() => { addToPlanner(r); setIsSelectingFor(null); setManualSearchResults([]); setManualSearchQuery(''); }} style={{borderStyle: 'dashed'}}>
                        <img src={r.image} className="card-img" style={{height:'80px'}} />
                        <div className="card-body" style={{padding: '8px'}}>
                          <p className="card-title" style={{fontSize:'12px', marginBottom: 0}}>{r.name}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : manualSearchQuery && !isManualSearchLoading && (
                  <p style={{color: '#4a7a4a', textAlign: 'center', fontSize: '14px'}}>No recipes found. Try a different keyword!</p>
                )}
              </div>
            )}

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
              
              {/* Daily Nutritional Totals Row */}
              <div className="grid-time" style={{fontSize: '10px', textTransform: 'uppercase', color: '#6ec86e'}}>Totals</div>
              {DAYS.map(d => {
                const stats = dailyStats[d] || {calories: 0, protein: 0, carbs: 0, fat: 0};
                return (
                  <div key={d} className="nutrition-summary" style={{margin: 0, borderRadius: 0, borderTop: '1px solid #000'}}>
                    <div className="nutrition-stat">
                      <span className="nutrition-value" style={{fontSize: '12px'}}>{Math.round(stats.calories)}</span>
                      <span style={{fontSize: '9px', opacity: 0.7}}>kcal</span>
                    </div>
                    <div style={{display:'flex', gap:'4px', fontSize:'9px', color:'#4a7a4a', justifyContent:'center'}}>
                      <span>P:{Math.round(stats.protein)}g</span>
                      <span>C:{Math.round(stats.carbs)}g</span>
                      <span>F:{Math.round(stats.fat)}g</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {weeklyStats && weeklyStats.calories > 0 && (
              <div className="weekly-summary-card">
                <h3 style={{color:'#6ec86e', margin:0, marginBottom: '16px'}}>Weekly Nutritional Profile</h3>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '24px'}}>
                   <div style={{background: '#080d08', padding: '16px', borderRadius: '16px', border: '1px solid #1c301c', textAlign: 'center'}}>
                      <div style={{fontSize: '12px', color: '#4a7a4a', marginBottom: '4px'}}>Total Calories</div>
                      <div style={{fontSize: '24px', fontWeight: '800', color: '#6ec86e'}}>{Math.round(weeklyStats.calories)} <span style={{fontSize:'12px'}}>kcal</span></div>
                   </div>
                   <div style={{background: '#080d08', padding: '16px', borderRadius: '16px', border: '1px solid #1c301c', textAlign: 'center'}}>
                      <div style={{fontSize: '12px', color: '#4a7a4a', marginBottom: '4px'}}>Total Protein</div>
                      <div style={{fontSize: '24px', fontWeight: '800', color: '#6ec86e'}}>{Math.round(weeklyStats.protein)} <span style={{fontSize:'12px'}}>g</span></div>
                   </div>
                   <div style={{background: '#080d08', padding: '16px', borderRadius: '16px', border: '1px solid #1c301c', textAlign: 'center'}}>
                      <div style={{fontSize: '12px', color: '#4a7a4a', marginBottom: '4px'}}>Total Carbs</div>
                      <div style={{fontSize: '24px', fontWeight: '800', color: '#6ec86e'}}>{Math.round(weeklyStats.carbs)} <span style={{fontSize:'12px'}}>g</span></div>
                   </div>
                   <div style={{background: '#080d08', padding: '16px', borderRadius: '16px', border: '1px solid #1c301c', textAlign: 'center'}}>
                      <div style={{fontSize: '12px', color: '#4a7a4a', marginBottom: '4px'}}>Total Fat</div>
                      <div style={{fontSize: '24px', fontWeight: '800', color: '#6ec86e'}}>{Math.round(weeklyStats.fat)} <span style={{fontSize:'12px'}}>g</span></div>
                   </div>
                </div>
              </div>
            )}

            <div style={{marginTop: '48px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px'}}>
              <div style={{background: '#0f180f', padding: '32px', borderRadius: '24px', border: '1px solid #1c301c'}}>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px'}}>
                  <h3 style={{color:'#6ec86e', margin:0}}>Grocery List</h3>
                  <div style={{display:'flex', gap:'8px', alignItems:'center'}}>
                    <select 
                      value={unitSystem} 
                      onChange={(e) => setUnitSystem(e.target.value)}
                      style={{background: '#080d08', color: '#6ec86e', border: '1px solid #1c301c', padding: '4px 8px', borderRadius: '8px', fontSize: '12px'}}
                    >
                      <option value="imperial">Imperial</option>
                      <option value="metric">Metric</option>
                    </select>
                    <button className="apply-plan-btn" style={{marginTop:0}} onClick={fetchGroceryList} disabled={isGroceryLoading}>
                      {isGroceryLoading ? 'Consolidating...' : '🛒 Generate'}
                    </button>
                  </div>
                </div>
                {Object.keys(groceryList).length > 0 ? (
                  <div className="grocery-categories">
                    {Object.entries(groceryList).map(([category, items]) => (
                      <div key={category} style={{marginBottom: '24px'}}>
                        <h4 style={{color: '#4a7a4a', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px', borderBottom: '1px solid #1c301c', paddingBottom: '4px'}}>{category}</h4>
                        <ul className="grocery-list">
                          {Array.isArray(items) && items.map((item, i) => (
                            <li key={i} className="grocery-item">
                              <input type="checkbox" style={{width:'20px', height:'20px', accentColor:'#2a6a2a'}} />
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{textAlign:'center', color:'#4a7a4a'}}>Click generate to consolidate ingredients!</p>
                )}
              </div>

              <div style={{background: '#0f180f', padding: '32px', borderRadius: '24px', border: '1px solid #1c301c'}}>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px'}}>
                  <h3 style={{color:'#6ec86e', margin:0}}>Meal Prep Guide</h3>
                  <button className="apply-plan-btn" style={{marginTop:0, background:'#4285F4'}} onClick={fetchPrepGuide} disabled={isPrepLoading}>
                    {isPrepLoading ? 'Analyzing...' : '🔪 Generate Prep Guide'}
                  </button>
                </div>
                <p style={{textAlign:'center', color:'#4a7a4a', marginTop: '20px', fontSize: '14px'}}>
                  Your consolidated prep plan will appear in a popup for easy reading.
                </p>
              </div>
            </div>

            <div style={{marginTop:'40px'}}>
              <h3 style={{color:'#6ec86e'}}>Suggestions for you</h3>
              <div className="recipe-grid">
                {recommendations.map(r => (
                  <div key={r.id} className="recipe-card" onClick={() => isSelectingFor ? addToPlanner(r) : setSelectedRecipe(r)}>
                    <img 
                      src={r.image || 'https://placehold.co/250x120?text=No+Image'} 
                      className="card-img" 
                      onError={(e) => { e.target.src = `https://placehold.co/250x120?text=${encodeURIComponent(r.name || r.title || 'Recipe')}`; }}
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
                    onError={(e) => { e.target.src = `https://placehold.co/250x120?text=${encodeURIComponent(r.name || r.title || 'Recipe')}`; }}
                  />
                  <div className="card-body"><p className="card-title">{r.name}</p></div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {showPrepModal && (
        <div className="modal-overlay" onClick={() => setShowPrepModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{maxWidth: '700px'}}>
            <button className="close-modal" onClick={() => setShowPrepModal(false)}>✕</button>
            <div className="modal-content">
              <div style={{display:'flex', alignItems:'center', gap:'12px', marginBottom:'24px'}}>
                <span style={{fontSize:'32px'}}>🔪</span>
                <h2 style={{color:'#6ec86e', margin:0}}>Your Weekly Meal Prep Guide</h2>
              </div>
              <div style={{
                color: '#e0d8c8', 
                fontSize: '15px', 
                lineHeight: '1.8',
                background: '#080d08',
                padding: '24px',
                borderRadius: '16px',
                border: '1px solid #1c301c'
              }}>
                <div className="prep-guide-content">
                  {Array.isArray(prepGuide) && prepGuide.length > 0 ? (
                    <table className="prep-table">
                      <thead>
                        <tr>
                          <th style={{width: '40px'}}></th>
                          <th className="step-col">Step</th>
                          <th className="task-col">Task</th>
                          <th className="meal-col">Related Meal(s)</th>
                          <th className="tip-col">Efficiency Tip</th>
                        </tr>
                      </thead>
                      <tbody>
                        {prepGuide.map((item, idx) => {
                          const isChecked = prepGuideChecked[idx] || false;
                          return (
                            <tr key={idx} style={{ opacity: isChecked ? 0.5 : 1 }}>
                              <td style={{ verticalAlign: 'middle', textAlign: 'center' }}>
                                <input 
                                  type="checkbox" 
                                  checked={isChecked}
                                  onChange={() => setPrepGuideChecked(prev => ({ ...prev, [idx]: !isChecked }))}
                                  style={{ width: '18px', height: '18px', accentColor: '#6ec86e', cursor: 'pointer' }}
                                />
                              </td>
                              <td className="step-col" style={{ textDecoration: isChecked ? 'line-through' : 'none' }}>{item.step || idx + 1}</td>
                              <td className="task-col" style={{ textDecoration: isChecked ? 'line-through' : 'none' }}>{item.task}</td>
                              <td className="meal-col">{item.meal_name}</td>
                              <td className="tip-col">{item.efficiency_tip}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  ) : typeof prepGuide === 'string' && prepGuide.length > 0 ? (
                    <div style={{whiteSpace: 'pre-wrap', padding: '16px'}}>{prepGuide}</div>
                  ) : (
                    <p style={{textAlign:'center', color:'#4a7a4a'}}>No structured steps generated. Try adding more recipes to your week!</p>
                  )}
                </div>
              </div>
              <button 
                className="fav-btn add" 
                style={{width:'100%', marginTop:'24px'}} 
                onClick={() => setShowPrepModal(false)}
              >
                Got it, Chef!
              </button>
            </div>
          </div>
        </div>
      )}

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
              
              <div style={{marginTop: '16px', display: 'flex', alignItems: 'center', gap: '12px', background: '#080d08', padding: '12px 20px', borderRadius: '12px', border: '1px solid #1c301c'}}>
                 <label style={{fontSize: '14px', color: '#6ec86e', fontWeight: 700, minWidth: '100px'}}>Servings: {modalServings}</label>
                 <input type="range" min="1" max="12" value={modalServings} onChange={(e) => setModalServings(parseInt(e.target.value))} style={{accentColor: '#6ec86e', flex: 1, cursor: 'pointer'}} />
              </div>

              <div style={{display: 'flex', gap: '12px', marginTop: '16px'}}>
                <button className={`fav-btn ${isFav(selectedRecipe.id) ? 'remove' : 'add'}`} onClick={() => toggleFavorite(selectedRecipe)} style={{marginTop: 0, flex: 1}}>
                  {isFav(selectedRecipe.id) ? '✕ Remove Favorite' : '❤ Add to Favorites'}
                </button>
                {isSelectingFor && (
                  <button className="fav-btn add" onClick={() => addToPlanner(selectedRecipe)} style={{marginTop: 0, flex: 1, background: '#4285F4'}}>
                    📅 Add to Planner
                  </button>
                )}
              </div>

              {selectedRecipe.nutrition && (
                <div style={{marginTop: '24px', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', background: 'rgba(110, 200, 110, 0.05)', padding: '16px', borderRadius: '16px', border: '1px solid #1c301c'}}>
                   <div style={{textAlign:'center'}}><div style={{fontSize:'10px', color:'#4a7a4a', fontWeight: 'bold', marginBottom: '4px'}}>CALORIES</div><div style={{color:'#6ec86e', fontWeight:700, fontSize: '18px'}}>{Math.round((selectedRecipe.nutrition.calories || 0) * (modalServings / 4))}</div></div>
                   <div style={{textAlign:'center'}}><div style={{fontSize:'10px', color:'#4a7a4a', fontWeight: 'bold', marginBottom: '4px'}}>PROTEIN</div><div style={{color:'#6ec86e', fontWeight:700, fontSize: '18px'}}>{Math.round((selectedRecipe.nutrition.protein || 0) * (modalServings / 4))}g</div></div>
                   <div style={{textAlign:'center'}}><div style={{fontSize:'10px', color:'#4a7a4a', fontWeight: 'bold', marginBottom: '4px'}}>CARBS</div><div style={{color:'#6ec86e', fontWeight:700, fontSize: '18px'}}>{Math.round((selectedRecipe.nutrition.carbs || 0) * (modalServings / 4))}g</div></div>
                   <div style={{textAlign:'center'}}><div style={{fontSize:'10px', color:'#4a7a4a', fontWeight: 'bold', marginBottom: '4px'}}>FAT</div><div style={{color:'#6ec86e', fontWeight:700, fontSize: '18px'}}>{Math.round((selectedRecipe.nutrition.fat || 0) * (modalServings / 4))}g</div></div>
                </div>
              )}

              <div style={{marginTop:'24px', display:'grid', gridTemplateColumns:'1fr 2fr', gap:'40px'}}>
                <div>
                  <h3 style={{color: '#6ec86e', borderBottom: '1px solid #1c301c', paddingBottom: '8px'}}>Ingredients</h3>
                  <ul style={{listStyle: 'none', padding: 0}}>
                    {(selectedRecipe.ingredients || []).map((ing, i) => (
                      <li key={i} style={{padding: '8px 0', borderBottom: '1px solid rgba(28, 48, 28, 0.5)', fontSize: '14px'}}>
                        <span style={{fontWeight: 700, color: '#6ec86e'}}>
                          {typeof ing === 'object' ? scaleQuantity(ing.qty, modalServings / 4) : ing}
                        </span> {typeof ing === 'object' ? ing.item : ''}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 style={{color: '#6ec86e', borderBottom: '1px solid #1c301c', paddingBottom: '8px'}}>Instructions</h3>
                  <p style={{whiteSpace:'pre-wrap', lineHeight: '1.6', fontSize: '15px'}}>{selectedRecipe.instructions}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
