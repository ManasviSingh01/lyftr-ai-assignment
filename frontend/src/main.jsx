import React, {useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App(){
  const sessionId = useMemo(() => `s-${crypto.randomUUID()}`, []);
  const [messages,setMessages]=useState([]); const [text,setText]=useState(''); const [systemPrompt,setSystemPrompt]=useState(''); const [loading,setLoading]=useState(false);
  async function send(){
    const message=text.trim(); if(!message || loading) return;
    setMessages(m=>[...m,{role:'user',content:message}]); setText(''); setLoading(true);
    try{
      const payload={session_id:sessionId,message}; if(systemPrompt.trim()) payload.system_prompt=systemPrompt.trim();
      const r=await fetch(`${API}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const data=await r.json(); if(!r.ok) throw new Error(data.detail || 'Request failed');
      setMessages(m=>[...m,{role:'assistant',content:data.reply,metadata:data.metadata}]);
    }catch(e){setMessages(m=>[...m,{role:'error',content:`Error: ${e.message}`}]);}finally{setLoading(false);}
  }
  return <main><header><div><span className="eyebrow">LYFTR AI</span><h1>Resilient AI Chat</h1><p>Multi-turn chat with key failover, response caching and request-level telemetry.</p></div><span className="status">● Ready</span></header>
    <section className="prompt"><label>Session system prompt <span>optional</span></label><input data-testid="system-prompt-input" value={systemPrompt} onChange={e=>setSystemPrompt(e.target.value)} placeholder="You are a helpful assistant..."/></section>
    <section className="chat">
      {messages.length===0 && <div className="empty"><div>✦</div><h2>Start a conversation</h2><p>Ask anything. Metadata for every AI response will appear below it.</p></div>}
      {messages.map((m,i)=> m.role==='assistant' ? <div className="row assistant" key={i}><div data-testid="assistant-message" className="bubble"><div className="reply">{m.content}</div><div className="meta"><span data-testid="meta-source" className={m.metadata.resolution_source==='LLM_CACHE'?'cache':'live'}>{m.metadata.resolution_source}</span><span data-testid="meta-model">{m.metadata.model}</span><span data-testid="meta-latency">{m.metadata.latency_ms} ms</span><span>IN <b data-testid="meta-input-tokens">{m.metadata.input_tokens}</b></span><span>OUT <b data-testid="meta-output-tokens">{m.metadata.output_tokens}</b></span></div></div></div> : <div className={`row ${m.role}`} key={i}><div className="bubble">{m.content}</div></div>)}
      {loading && <div className="row assistant"><div className="bubble typing">Thinking…</div></div>}
    </section>
    <section className="composer"><textarea data-testid="chat-input" value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}}} placeholder="Message Lyftr AI..."/><button data-testid="send-button" onClick={send} disabled={loading || !text.trim()}>Send ↑</button></section>
    <footer>Session <code>{sessionId.slice(0,18)}…</code> · New session on every page load</footer>
  </main>
}
createRoot(document.getElementById('root')).render(<App/>);
