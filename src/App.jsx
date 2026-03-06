import React, { useState, useEffect } from 'react';

const BACKEND_URL = "http://127.0.0.1:8000";

const css = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  body { font-family: 'Inter', sans-serif; margin: 0; background: #080d08; color: #e0d8c8; }
  .app-container { display: flex; flex-direction: column; min-height: 100vh; }
  
  /* Nav */
  .nav { border-bottom: 1px solid #1c301c; padding: 24px; display: flex; justify-content: space-between; align-items: center; background: rgba(8, 13, 8, 0.8); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 50; }
  .logo-container { display: flex; items-center; gap: 12px; }
  .logo-icon { width: 40px; height: 40px; background: #2a6a2a; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 24px; box-shadow: 0 4px 12px rgba(42, 106, 42, 0.2); }
  .logo-text h1 { font-size: 24px; font-weight: 700; color: #6ec86e; margin: 0; }
  .logo-sub { font-size: 10px; color: #4a7a4a; text-transform: uppercase; letter-spacing: 2px; font-weight: 700; }
  
  .tab-bar { display: flex; gap: 8px; background: #0f180f; padding: 4px; border-radius: 12px; border: 1px solid #1c301c; }
  .tab-btn { padding: 8px 20px; border-radius: 8px; border: none; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; color: #4a7a4a; background: transparent; }
  .tab-btn.active { background: #2a6a2a; color: white; }
  .tab-btn:hover:not(.active) { color: #6ec86e; }

  /* Main */
  .main { max-width: 1100px; margin: 0 auto; padding: 24px; width: 100%; box-sizing: border-box; }
  
  /* Chat */
  .chat-box { background: #0f180f; border: 1px solid #1c301c; border-radius: 24px; height: 700px; display: flex; flex-direction: column; box-shadow: 0 10px 30px rgba(0,0,0,0.5); overflow: hidden; position: relative; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 32px; display: flex; flex-direction: column; gap: 32px; }
  
  .message { display: flex; }
  .message.user { justify-content: flex-end; }
  .message.assistant { justify-content: flex-start; }
  
  .bubble { max-width: 85%; padding: 20px; border-radius: 24px; font-size: 15px; line-height: 1.6; }
  .user .bubble { background: #2a6a2a; color: white; box-shadow: 0 4px 15px rgba(42, 106, 42, 0.2); }
  .assistant .bubble { background: #1c301c; color: #e0d8c8; border: 1px solid rgba(110, 200, 110, 0.1); }
  
  /* Cards */
  .recipe-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 24px; }
  .recipe-card { background: #080d08; border-radius: 16px; border: 1px solid rgba(42, 106, 42, 0.3); overflow: hidden; cursor: pointer; transition: all 0.2s; }
  .recipe-card:hover { border-color: #6ec86e; transform: translateY(-2px); }
  .card-img { width: 100%; height: 128px; object-fit: cover; opacity: 0.8; }
  .card-placeholder { width: 100%; height: 128px; background: #1c301c; display: flex; items-center; justify-content: center; font-size: 32px; }
  .card-content { padding: 16px; }
  .card-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px; }
  .card-title { font-weight: 700; color: #6ec86e; font-size: 14px; margin: 0; }
  .card-tag { font-size: 9px; background: #1c301c; padding: 2px 8px; border-radius: 99px; color: #6ec86e; text-transform: uppercase; font-weight: 700; }
  .card-meta { display: flex; gap: 8px; font-size: 10px; color: #4a7a4a; }

  /* Input */
  .chat-input-area { padding: 24px; border-top: 1px solid #1c301c; background: rgba(15, 24, 15, 0.5); }
  .input-wrapper { display: flex; gap: 12px; background: #080d08; padding: 8px; border-radius: 16px; border: 1px solid #1c301c; }
  .input-wrapper:focus-within { border-color: #2a6a2a; }
  .chat-input { flex: 1; background: transparent; border: none; outline: none; padding: 8px 16px; color: #e0d8c8; font-size: 14px; }
  .send-btn { background: #2a6a2a; color: white; border: none; padding: 10px 24px; border-radius: 12px; font-weight: 700; cursor: pointer; transition: background 0.2s; }
  .send-btn:hover { background: #3a7a3a; }
  .send-btn:disabled { opacity: 0.5; cursor: default; }

  /* Empty State */
  .empty-state { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #4a7a4a; gap: 16px; }
  .suggestion-chips { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; max-width: 400px; }
  .chip { background: #1c301c; border: 1px solid rgba(42, 106, 42, 0.2); color: #6ec86e; padding: 8px 16px; border-radius: 99px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
  .chip:hover { background: rgba(42, 106, 42, 0.3); border-color: #6ec86e; }

  /* Modal */
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.9); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 24px; }
  .modal { background: #0f180f; border: 1px solid #1c301c; border-radius: 40px; max-width: 900px; width: 100%; max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; }
  .modal-header { height: 280px; position: relative; flex-shrink: 0; }
  .modal-img { width: 100%; height: 100%; object-fit: cover; }
  .modal-gradient { position: absolute; inset: 0; background: linear-gradient(to top, #0f180f, transparent); }
  .close-btn { position: absolute; top: 24px; right: 24px; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.1); width: 48px; height: 48px; border-radius: 50%; color: white; cursor: pointer; }
  .modal-title-box { position: absolute; bottom: 24px; left: 32px; }
  .modal-body { padding: 40px; overflow-y: auto; display: grid; grid-template-columns: 2fr 3fr; gap: 48px; }
  
  .section-title { font-size: 18px; font-weight: 700; color: #6ec86e; margin-bottom: 24px; display: flex; items-center; gap: 12px; }
  .ingredient-list { background: #080d08; padding: 24px; border-radius: 20px; border: 1px solid #1c301c; }
  .ing-row { display: flex; justify-content: space-between; border-bottom: 1px solid #1c301c; padding: 12px 0; font-size: 14px; }
  .ing-qty { color: #6ec86e; font-weight: 600; }
  .instructions-box { background: rgba(28, 48, 28, 0.3); padding: 32px; border-radius: 24px; border: 1px solid rgba(42, 106, 42, 0.1); line-height: 1.8; font-size: 15px; white-space: pre-wrap; }

  /* Loading Dots */
  .dots { display: flex; gap: 4px; padding: 12px 20px; background: #1c301c; border-radius: 24px; border: 1px solid rgba(110, 200, 110, 0.2); width: fit-content; }
  .dot { width: 6px; height: 6px; background: #6ec86e; border-radius: 50%; animation: bounce 1.4s infinite ease-in-out; }
  @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
`;

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedRecipe, setSelectedRecipe] = useState(null);

  const handleChat = async (overrideMsg = null) => {
    const msg = overrideMsg || chatInput;
    if (!msg.trim() || loading) return;
    
    const userMsg = { role: 'user', content: msg };
    setChatHistory(prev => [...prev, userMsg]);
    if (!overrideMsg) setChatInput('');
    setLoading(true);

    try {
      const res = await fetch(`${BACKEND_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: msg,
          history: chatHistory.slice(-5).map(m => ({ role: m.role, content: m.content }))
        }),
      });
      
      const data = await res.json();
      setChatHistory(prev => [...prev, { role: 'assistant', content: data.message, recipes: data.recipes || [] }]);
    } catch (err) {
      setChatHistory(prev => [...prev, { role: 'assistant', content: "Backend error. Please ensure nourish_backend.py is running!" }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      <style>{css}</style>

      <nav className="nav">
        <div className="logo-container">
          <div className="logo-icon">🌿</div>
          <div className="logo-text">
            <h1>NourishAI</h1>
            <div className="logo-sub">RAG Recipe Intelligence</div>
          </div>
        </div>
        <div className="tab-bar">
          {['chat', 'planner', 'recommend'].map(t => (
            <button key={t} onClick={() => setActiveTab(t)} className={`tab-btn ${activeTab === t ? 'active' : ''}`}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </nav>

      <main className="main">
        {activeTab === 'chat' ? (
          <div className="chat-box">
            <div className="chat-messages">
              {chatHistory.length === 0 && (
                <div className="empty-state">
                  <div style={{ fontSize: '64px' }}>🍲</div>
                  <h2>What shall we cook today?</h2>
                  <p>I'm your RAG-powered chef. Ask me about your 697+ recipes.</p>
                  <div className="suggestion-chips">
                    {["Turkish kebabs", "Healthy breakfast", "Seafood dinner", "Spicy chicken"].map(s => (
                      <div key={s} className="chip" onClick={() => handleChat(s)}>"{s}"</div>
                    ))}
                  </div>
                </div>
              )}
              
              {chatHistory.map((msg, i) => (
                <div key={i} className={`message ${msg.role}`}>
                  <div className="bubble">
                    {msg.content}
                    {msg.recipes && msg.recipes.length > 0 && (
                      <div className="recipe-grid">
                        {msg.recipes.map((r, idx) => (
                          <div key={idx} className="recipe-card" onClick={() => setSelectedRecipe(r)}>
                            {r.image ? <img src={r.image} className="card-img" /> : <div className="card-placeholder">🍳</div>}
                            <div className="card-content">
                              <div className="card-header">
                                <h4 className="card-title">{r.name}</h4>
                                <span className="card-tag">{r.category}</span>
                              </div>
                              <div className="card-meta">
                                <span>🌍 {r.cuisine}</span>
                                <span>🕒 30m</span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              
              {loading && (
                <div className="message assistant">
                  <div className="dots">
                    <div className="dot" style={{ animationDelay: '0s' }}></div>
                    <div className="dot" style={{ animationDelay: '0.2s' }}></div>
                    <div className="dot" style={{ animationDelay: '0.4s' }}></div>
                  </div>
                </div>
              )}
            </div>

            <div className="chat-input-area">
              <div className="input-wrapper">
                <input 
                  className="chat-input"
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyPress={e => e.key === 'Enter' && handleChat()}
                  placeholder="Ask for a recipe or meal idea..."
                />
                <button className="send-btn" onClick={() => handleChat()} disabled={loading}>Send ✦</button>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '100px 0', color: '#4a7a4a' }}>
            <div style={{ fontSize: '48px' }}>🚧</div>
            <h2>Planner & Recommendations</h2>
            <p>Currently optimizing the RAG chat engine. Try the chat!</p>
          </div>
        )}
      </main>

      {selectedRecipe && (
        <div className="modal-overlay" onClick={() => setSelectedRecipe(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              {selectedRecipe.image ? <img src={selectedRecipe.image} className="modal-img" /> : <div className="card-placeholder" style={{height:'100%'}}>🍲</div>}
              <div className="modal-gradient"></div>
              <button className="close-btn" onClick={() => setSelectedRecipe(null)}>✕</button>
              <div className="modal-title-box">
                <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                  <span className="card-tag" style={{ background: '#2a6a2a', color: 'white' }}>{selectedRecipe.category}</span>
                  <span className="card-tag" style={{ border: '1px solid #2a6a2a' }}>{selectedRecipe.cuisine}</span>
                </div>
                <h2 style={{ fontSize: '36px', margin: 0 }}>{selectedRecipe.name}</h2>
              </div>
            </div>
            <div className="modal-body">
              <div>
                <h3 className="section-title">🛒 Ingredients</h3>
                <div className="ingredient-list">
                  {selectedRecipe.ingredients.map((ing, i) => (
                    <div key={i} className="ing-row">
                      <span>{ing.item}</span>
                      <span className="ing-qty">{ing.qty}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="section-title">🍳 Instructions</h3>
                <div className="instructions-box">{selectedRecipe.instructions}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
