"""
Medical AI Bot Launcher - Clean Production Version
- Serves the UI
- Serves LiveKit tokens
- Bot workers run as separate processes via supervisord
"""

import os
import socket
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from livekit import api
from dotenv import load_dotenv

load_dotenv(override=True)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BOT_DIR = Path(__file__).parent
AUDIO_HTML = (BOT_DIR / "audio_ui.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def launcher_page():
    return HTMLResponse(content=LAUNCHER_HTML)


@app.get("/audio", response_class=HTMLResponse)
def audio_page():
    return HTMLResponse(content=AUDIO_HTML)


@app.get("/video", response_class=HTMLResponse)
def video_page():
    return HTMLResponse(content=VIDEO_HTML)


@app.post("/token")
async def get_token(request: Request):
    try:
        data = await request.json()
        room_name = data.get("room", "dev-room")
        participant_name = data.get("participant_name", "User")
        mode = data.get("mode", "")
    except Exception:
        room_name = "dev-room"
        participant_name = "User"
        mode = ""

    mode_qp = request.query_params.get("mode", mode)
    if mode_qp == "audio" and not room_name.startswith("audio-room"):
        room_name = "audio-room-" + room_name

    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not livekit_api_key or not livekit_api_secret or not livekit_url:
        return JSONResponse({"error": "Missing LiveKit credentials"}, status_code=500)

    token = api.AccessToken(livekit_api_key, livekit_api_secret) \
        .with_identity(participant_name) \
        .with_name(participant_name) \
        .with_grants(api.VideoGrants(room_join=True, room=room_name)) \
        .to_jwt()

    return JSONResponse({"token": token, "url": livekit_url, "room": room_name})


@app.get("/status")
def bot_status():
    return JSONResponse({"running": True, "mode": "audio"})


LAUNCHER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Medical AI Bot</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Inter',sans-serif;background:#050b18;color:#e2e8f0;min-height:100vh;
    display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2rem;
    background-image:radial-gradient(ellipse at 20% 20%,rgba(59,130,246,.08) 0%,transparent 50%),
    radial-gradient(ellipse at 80% 80%,rgba(139,92,246,.08) 0%,transparent 50%)}
  h1{font-size:2.2rem;font-weight:800;background:linear-gradient(135deg,#60a5fa,#a78bfa,#34d399);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:.4rem;text-align:center}
  .subtitle{color:#64748b;font-size:1rem;margin-bottom:3rem;text-align:center}
  .cards{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;width:100%;max-width:700px;margin-bottom:2rem}
  .card{background:#0d1629;border:1.5px solid rgba(99,179,237,.12);border-radius:20px;padding:2rem;text-align:center;transition:all .3s;text-decoration:none;display:block;color:inherit}
  .card:hover{transform:translateY(-4px)}
  .card.audio:hover{border-color:rgba(59,130,246,.5);box-shadow:0 20px 60px rgba(59,130,246,.15)}
  .card.video:hover{border-color:rgba(139,92,246,.5);box-shadow:0 20px 60px rgba(139,92,246,.15)}
  .card-icon{font-size:3rem;margin-bottom:1rem;display:block}
  .card-title{font-size:1.3rem;font-weight:700;margin-bottom:.5rem}
  .card.audio .card-title{color:#60a5fa}.card.video .card-title{color:#a78bfa}
  .card-desc{color:#64748b;font-size:.875rem;line-height:1.6;margin-bottom:1.5rem}
  .tag{display:inline-block;padding:.2rem .7rem;border-radius:99px;font-size:.75rem;font-weight:600;margin:.2rem}
  .tag-blue{background:rgba(59,130,246,.15);color:#60a5fa}
  .tag-purple{background:rgba(139,92,246,.15);color:#a78bfa}
  .tag-teal{background:rgba(20,184,166,.15);color:#34d399}
  .btn{display:block;width:100%;padding:.85rem 1.5rem;border:none;border-radius:12px;font-family:'Inter',sans-serif;
    font-size:.95rem;font-weight:600;cursor:pointer;transition:all .2s;margin-top:1rem;text-align:center;text-decoration:none}
  .btn-audio{background:linear-gradient(135deg,#2563eb,#3b82f6);color:white}
  .btn-video{background:linear-gradient(135deg,#7c3aed,#8b5cf6);color:white}
  .btn:hover{transform:scale(1.03);filter:brightness(1.1)}
  .live-badge{display:inline-flex;align-items:center;gap:.4rem;background:rgba(34,197,94,.15);
    color:#4ade80;border:1px solid rgba(34,197,94,.3);padding:.3rem .8rem;border-radius:99px;font-size:.8rem;font-weight:600;margin-bottom:1rem}
  .live-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>
<h1>🩺 Medical AI Bot</h1>
<p class="subtitle">Dr. Alex is live — choose your mode</p>

<div class="cards">
  <a class="card audio" href="/audio">
    <span class="card-icon">🎙️</span>
    <div class="live-badge"><span class="live-dot"></span> Live</div>
    <div class="card-title">Audio Bot</div>
    <p class="card-desc">Voice conversation with Dr. Alex. Speak naturally, get instant replies.</p>
    <div>
      <span class="tag tag-blue">Deepgram STT</span>
      <span class="tag tag-teal">Cartesia TTS</span>
      <span class="tag tag-blue">Groq LLM</span>
    </div>
    <span class="btn btn-audio">Open Audio Bot →</span>
  </a>

  <a class="card video" href="/video">
    <span class="card-icon">🎬</span>
    <div class="live-badge"><span class="live-dot"></span> Live</div>
    <div class="card-title">Video Avatar Bot</div>
    <p class="card-desc">Talk to Dr. Alex's 3D avatar with lip-sync powered by SpatialReal.</p>
    <div>
      <span class="tag tag-purple">SpatialReal Avatar</span>
      <span class="tag tag-teal">Cartesia TTS</span>
      <span class="tag tag-purple">Groq LLM</span>
    </div>
    <span class="btn btn-video">Open Video Bot →</span>
  </a>
</div>
</body>
</html>"""


VIDEO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dr. Alex - Video Avatar</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#f1f5f9;min-height:100vh;
    display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2rem}
  h1{color:#a78bfa;font-size:2rem;margin-bottom:.3rem}
  .subtitle{color:#64748b;margin-bottom:2rem;font-size:.95rem}
  .card{background:#1e293b;border-radius:20px;padding:2rem;width:100%;max-width:560px;text-align:center}
  .avatar{width:120px;height:120px;border-radius:50%;background:linear-gradient(135deg,#7c3aed,#a78bfa);
    display:flex;align-items:center;justify-content:center;font-size:3rem;margin:0 auto 1.5rem}
  .status{color:#94a3b8;font-size:.9rem;margin-bottom:1.5rem;min-height:1.2rem}
  .btn{width:100%;padding:1rem;border:none;border-radius:12px;font-size:1rem;font-weight:700;
    cursor:pointer;transition:.2s;background:linear-gradient(135deg,#7c3aed,#8b5cf6);color:white}
  .btn:hover{filter:brightness(1.1)}
  .btn.stop{background:#ef4444;display:none}
  .chatbox{height:200px;overflow-y:auto;background:#0f172a;border:1px solid #334155;
    border-radius:12px;padding:1rem;margin-bottom:1.5rem;display:flex;flex-direction:column;gap:.6rem;text-align:left}
  .msg{padding:.6rem 1rem;border-radius:10px;max-width:85%;font-size:.875rem}
  .bot-msg{background:#334155;align-self:flex-start}
  .user-msg{background:#7c3aed;align-self:flex-end}
  .back{color:#64748b;font-size:.85rem;margin-top:1rem;text-decoration:none}
  .back:hover{color:#94a3b8}
</style>
<script src="https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.min.js"></script>
</head>
<body>
<h1>🎬 Dr. Alex</h1>
<p class="subtitle">3D Avatar Medical Assistant</p>
<div class="card">
  <div class="avatar" id="avatar">🩺</div>
  <div class="chatbox" id="chatbox">
    <div class="msg bot-msg">Hello! I'm Dr. Alex. Click Start to begin.</div>
  </div>
  <div class="status" id="status">Ready</div>
  <button class="btn" id="startBtn" onclick="startConversation()">🎙️ Start Conversation</button>
  <button class="btn stop" id="stopBtn" onclick="stopConversation()">⏹ Disconnect</button>
</div>
<a class="back" href="/">← Back to launcher</a>

<script>
let room=null, audioElements=[], audioCtx=null;
const statusEl=document.getElementById('status');
const startBtn=document.getElementById('startBtn');
const stopBtn=document.getElementById('stopBtn');
const avatar=document.getElementById('avatar');
const chatbox=document.getElementById('chatbox');

function addMsg(text,isUser){
  const el=document.createElement('div');
  el.className='msg '+(isUser?'user-msg':'bot-msg');
  el.textContent=text; chatbox.appendChild(el);
  chatbox.scrollTop=chatbox.scrollHeight;
}
function getOrUpdateMsg(id,text,isUser){
  let el=document.getElementById('msg_'+id);
  if(!el){el=document.createElement('div');el.id='msg_'+id;el.className='msg '+(isUser?'user-msg':'bot-msg');chatbox.appendChild(el);}
  el.textContent=text; chatbox.scrollTop=chatbox.scrollHeight;
}

async function startConversation(){
  startBtn.disabled=true; statusEl.textContent='Connecting...';
  try{
    audioCtx=new(window.AudioContext||window.webkitAudioContext)();
    const roomName='video-room-'+Math.random().toString(36).substring(2,9);
    const res=await fetch('/token',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({room:roomName,mode:'video',participant_name:'User'})});
    const data=await res.json();
    if(!data.token||!data.url) throw new Error('Token failed');

    room=new LivekitClient.Room({adaptiveStream:true,dynacast:true});

    room.on(LivekitClient.RoomEvent.TrackSubscribed,(track,pub,participant)=>{
      if(track.kind===LivekitClient.Track.Kind.Audio){
        const el=track.attach();
        el.autoplay=true; el.muted=false; el.volume=1.0;
        document.body.appendChild(el); audioElements.push(el);
        el.play().catch(()=>{});
      }
      if(track.kind===LivekitClient.Track.Kind.Video){
        const el=track.attach();
        el.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:-1;opacity:.3';
        document.body.appendChild(el);
      }
    });

    room.on(LivekitClient.RoomEvent.ActiveSpeakersChanged,(speakers)=>{
      const agentSpeaking=speakers.some(s=>s.identity.startsWith('agent'));
      avatar.style.boxShadow=agentSpeaking?'0 0 30px #a78bfa':'none';
      statusEl.textContent=agentSpeaking?'🔊 Dr. Alex is speaking...':'💬 Speak to Dr. Alex...';
    });

    room.on(LivekitClient.RoomEvent.TranscriptionReceived,(segments,participant)=>{
      const isAgent=participant&&participant.identity.startsWith('agent');
      for(const seg of segments) getOrUpdateMsg(seg.id,seg.text,!isAgent);
    });

    room.on(LivekitClient.RoomEvent.ParticipantConnected,(p)=>{
      if(p.identity.startsWith('agent')) statusEl.textContent='🤖 Dr. Alex joined!';
    });

    await room.connect(data.url,data.token);
    await room.localParticipant.setMicrophoneEnabled(true);
    statusEl.textContent='⏳ Waiting for Dr. Alex...';
    startBtn.style.display='none'; stopBtn.style.display='block';
  }catch(e){
    statusEl.textContent='Error: '+e.message;
    startBtn.disabled=false;
  }
}

async function stopConversation(){
  if(room){await room.disconnect();room=null;}
  audioElements.forEach(el=>{el.pause();el.remove();}); audioElements=[];
  if(audioCtx){audioCtx.close();audioCtx=null;}
  startBtn.style.display='block'; startBtn.disabled=false;
  stopBtn.style.display='none'; statusEl.textContent='Disconnected';
  avatar.style.boxShadow='none';
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Starting Medical AI Bot Launcher on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
