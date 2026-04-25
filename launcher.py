"""
Medical AI Bot Launcher - Production Version
Single process: FastAPI + LiveKit bot workers via asyncio background tasks
"""

import os
import sys
import asyncio
import socket
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from livekit import api
from dotenv import load_dotenv

load_dotenv(override=True)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BOT_DIR = Path(__file__).parent
AUDIO_HTML = (BOT_DIR / "audio_ui.html").read_text(encoding="utf-8")

# Global state
current_mode = None
bot_task = None  # asyncio Task


# ─── Bot worker factories ────────────────────────────────────────────────────

async def run_audio_worker():
    from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions
    from livekit.agents.worker import Worker
    from livekit.plugins import cartesia, deepgram, silero
    from livekit.plugins.openai import LLM

    SYSTEM_PROMPT = """You are Dr. Alex, a warm professional AI medical assistant.
Keep responses SHORT (5-15 words). Be friendly and helpful."""

    class AudioAgent(Agent):
        def __init__(self):
            super().__init__(instructions=SYSTEM_PROMPT)

    async def entrypoint(ctx: JobContext):
        print(f"[Audio] Connecting to room: {ctx.room.name}")
        await ctx.connect()
        llm = LLM(api_key=os.getenv("GROQ_API_KEY"),
                  base_url="https://api.groq.com/openai/v1",
                  model="llama-3.1-8b-instant")
        tts = cartesia.TTS(api_key=os.getenv("CARTESIA_API_KEY"),
                           voice="694f9389-aac1-45b6-b726-9d9369183238",
                           sample_rate=16000)
        stt = deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY"))
        vad = silero.VAD.load(min_silence_duration=0.6)
        session = AgentSession(llm=llm, tts=tts, stt=stt, vad=vad)
        await session.start(agent=AudioAgent(), room=ctx.room,
                            room_input_options=RoomInputOptions())
        await session.generate_reply(
            instructions="Greet the user and introduce yourself as Dr. Alex. Keep it short.")
        print("[Audio] Bot live!")

    opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
        ws_url=os.getenv("LIVEKIT_URL"),
    )
    worker = Worker(opts)
    await worker.run()


async def run_video_worker():
    from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions
    from livekit.agents.worker import Worker
    from livekit.plugins import cartesia, deepgram, silero, spatialreal
    from livekit.plugins.openai import LLM

    SYSTEM_PROMPT = """You are Dr. Alex, a warm professional AI medical assistant with a 3D avatar.
Keep responses EXTREMELY SHORT (under 10 words). Speak naturally."""

    class AvatarAgent(Agent):
        def __init__(self):
            super().__init__(instructions=SYSTEM_PROMPT)

    async def entrypoint(ctx: JobContext):
        print(f"[Video] Connecting to room: {ctx.room.name}")
        await ctx.connect()
        llm = LLM(api_key=os.getenv("GROQ_API_KEY"),
                  base_url="https://api.groq.com/openai/v1",
                  model="llama-3.1-8b-instant")
        tts = cartesia.TTS(api_key=os.getenv("CARTESIA_API_KEY"),
                           voice="694f9389-aac1-45b6-b726-9d9369183238",
                           sample_rate=24000)
        stt = deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY"))
        vad = silero.VAD.load(min_silence_duration=0.6)
        avatar = spatialreal.AvatarSession(
            api_key=os.getenv("SPATIALREAL_API_KEY"),
            app_id=os.getenv("SPATIALREAL_APP_ID"),
            avatar_id=os.getenv("SPATIALREAL_AVATAR_ID"),
            sample_rate=24000,
        )
        session = AgentSession(llm=llm, tts=tts, stt=stt, vad=vad)
        await avatar.start(session, room=ctx.room)
        await session.start(agent=AvatarAgent(), room=ctx.room,
                            room_input_options=RoomInputOptions())
        await session.generate_reply(
            instructions="Greet the user and introduce yourself as Dr. Alex.")
        print("[Video] Bot live!")

    opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
        ws_url=os.getenv("LIVEKIT_URL"),
    )
    worker = Worker(opts)
    await worker.run()


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def launcher_page():
    return HTMLResponse(content=LAUNCHER_HTML)


@app.get("/audio", response_class=HTMLResponse)
def audio_page():
    return HTMLResponse(content=AUDIO_HTML)


@app.get("/video", response_class=HTMLResponse)
def video_page():
    # Video bot uses SpatialReal's own frontend via LiveKit
    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Video Bot</title>
<style>body{background:#0f172a;color:#f1f5f9;font-family:sans-serif;display:flex;
align-items:center;justify-content:center;min-height:100vh;flex-direction:column;gap:1rem;}
.card{background:#1e293b;padding:2rem;border-radius:16px;text-align:center;max-width:500px;}
h2{color:#a78bfa;margin-bottom:1rem;}p{color:#94a3b8;margin-bottom:1.5rem;}
.btn{background:linear-gradient(135deg,#7c3aed,#8b5cf6);color:white;border:none;
padding:1rem 2rem;border-radius:12px;font-size:1rem;font-weight:700;cursor:pointer;}
</style></head>
<body>
<div class="card">
  <h2>🎬 Video Avatar Bot</h2>
  <p>Dr. Alex 3D Avatar is running. Use the LiveKit Meet link below to join with video.</p>
  <p id="info" style="color:#34d399;font-size:0.9rem;">Bot worker is active and waiting for you to join a room.</p>
  <br>
  <a href="/" style="color:#60a5fa;font-size:0.9rem;">← Back to launcher</a>
</div>
<script>
  // Auto-redirect to audio UI which works in browser
  // Video avatar requires LiveKit room join
</script>
</body></html>""")


@app.post("/start/{mode}")
async def start_bot(mode: str):
    global bot_task, current_mode

    if mode not in ("audio", "video"):
        return JSONResponse({"error": "Invalid mode"}, status_code=400)

    # Cancel existing bot task
    if bot_task and not bot_task.done():
        bot_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(bot_task), timeout=2.0)
        except:
            pass

    try:
        loop = asyncio.get_event_loop()
        if mode == "audio":
            bot_task = loop.create_task(run_audio_worker())
        else:
            bot_task = loop.create_task(run_video_worker())

        current_mode = mode
        return JSONResponse({"status": "started", "mode": mode})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/token")
async def get_token(request: Request):
    try:
        data = await request.json()
        room_name = data.get("room", "dev-room")
        participant_name = data.get("participant_name", "User")
        mode = data.get("mode", "")
    except:
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


@app.post("/stop")
async def stop_bot():
    global bot_task, current_mode
    if bot_task and not bot_task.done():
        bot_task.cancel()
    current_mode = None
    return JSONResponse({"status": "stopped"})


@app.get("/status")
def bot_status():
    running = bot_task is not None and not bot_task.done()
    return JSONResponse({"running": running, "mode": current_mode if running else None})


@app.get("/check-port/{port}")
def check_port_ready(port: int):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return JSONResponse({"ready": True})
    except:
        return JSONResponse({"ready": False})


# ─── Launcher HTML ────────────────────────────────────────────────────────────

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
  .card{background:#0d1629;border:1.5px solid rgba(99,179,237,.12);border-radius:20px;padding:2rem;text-align:center;transition:all .3s}
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
  .btn{width:100%;padding:.85rem 1.5rem;border:none;border-radius:12px;font-family:'Inter',sans-serif;
    font-size:.95rem;font-weight:600;cursor:pointer;transition:all .2s;margin-top:1rem}
  .btn-audio{background:linear-gradient(135deg,#2563eb,#3b82f6);color:white}
  .btn-video{background:linear-gradient(135deg,#7c3aed,#8b5cf6);color:white}
  .btn:hover{transform:scale(1.03);filter:brightness(1.1)}.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
  .spinner{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.3);
    border-top-color:white;border-radius:50%;animation:spin .8s linear infinite;margin-right:6px;vertical-align:middle}
  @keyframes spin{to{transform:rotate(360deg)}}
  .status-bar{background:#0d1629;border:1px solid rgba(99,179,237,.12);border-radius:12px;
    padding:1rem 1.5rem;width:100%;max-width:700px;display:flex;align-items:center;gap:1rem}
  .status-dot{width:10px;height:10px;border-radius:50%;background:#64748b;flex-shrink:0}
  .status-dot.running{background:#22c55e;box-shadow:0 0 8px #22c55e;animation:pulse 2s infinite}
  .status-dot.starting{background:#f59e0b;box-shadow:0 0 8px #f59e0b;animation:pulse 1s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
  .status-text{font-size:.875rem;color:#64748b;flex:1}
  .ready-banner{display:none;align-items:center;justify-content:space-between;gap:1rem;
    background:linear-gradient(135deg,rgba(34,197,94,.12),rgba(20,184,166,.08));
    border:1.5px solid rgba(34,197,94,.4);border-radius:16px;padding:1.2rem 1.8rem;
    width:100%;max-width:700px;margin-top:1rem}
  .open-now-btn{display:inline-block;padding:.75rem 1.8rem;background:linear-gradient(135deg,#16a34a,#22c55e);
    color:white;font-family:'Inter',sans-serif;font-size:1rem;font-weight:700;border-radius:12px;
    text-decoration:none;border:none;cursor:pointer;box-shadow:0 0 20px rgba(34,197,94,.4);transition:all .2s}
  .open-now-btn:hover{transform:scale(1.05)}
  .btn-stop{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3);
    padding:.4rem 1rem;border-radius:8px;font-size:.8rem;font-weight:600;cursor:pointer;font-family:'Inter',sans-serif}
</style>
</head>
<body>
<h1>🩺 Medical AI Bot</h1>
<p class="subtitle">Choose your interaction mode</p>
<div class="cards">
  <div class="card audio">
    <span class="card-icon">🎙️</span>
    <div class="card-title">Audio Bot</div>
    <p class="card-desc">Voice-only interaction. Fast and lightweight.</p>
    <div>
      <span class="tag tag-blue">Deepgram STT</span>
      <span class="tag tag-teal">Cartesia TTS</span>
      <span class="tag tag-blue">Groq LLM</span>
    </div>
    <button class="btn btn-audio" id="btn-audio" onclick="startBot('audio')">
      <span id="spin-audio" style="display:none"><span class="spinner"></span></span>Start Audio Bot
    </button>
  </div>
  <div class="card video">
    <span class="card-icon">🎬</span>
    <div class="card-title">Video Avatar Bot</div>
    <p class="card-desc">Live 3D avatar with lip-sync powered by SpatialReal.</p>
    <div>
      <span class="tag tag-purple">SpatialReal Avatar</span>
      <span class="tag tag-teal">Cartesia TTS</span>
      <span class="tag tag-purple">Groq LLM</span>
    </div>
    <button class="btn btn-video" id="btn-video" onclick="startBot('video')">
      <span id="spin-video" style="display:none"><span class="spinner"></span></span>Start Video Bot
    </button>
  </div>
</div>
<div class="status-bar">
  <div class="status-dot" id="status-dot"></div>
  <div class="status-text" id="status-text">No bot running. Choose a mode above.</div>
  <div id="action-btns"></div>
</div>
<div class="ready-banner" id="ready-banner">
  <div style="font-size:.95rem;color:#86efac;font-weight:600"><span style="font-size:1.3rem;margin-right:.5rem">✅</span>Bot is ready!</div>
  <a class="open-now-btn" id="ready-link" href="#" target="_blank">Open Bot →</a>
</div>
<script>
async function startBot(mode){
  const btn=document.getElementById('btn-'+mode);
  const spin=document.getElementById('spin-'+mode);
  btn.disabled=true; spin.style.display='inline';
  document.getElementById('ready-banner').style.display='none';
  try{
    const res=await fetch('/start/'+mode,{method:'POST'});
    const data=await res.json();
    if(data.status==='started'){
      updateStatus('starting',mode);
      setTimeout(()=>{updateStatus('running',mode);showBanner('/'+mode,mode);},8000);
    } else { alert('Error: '+(data.error||'Unknown')); }
  }catch(e){alert('Failed: '+e.message);}
  finally{btn.disabled=false;spin.style.display='none';}
}
function showBanner(url,mode){
  const banner=document.getElementById('ready-banner');
  const link=document.getElementById('ready-link');
  link.href=url; link.textContent='Open '+(mode==='audio'?'Audio':'Video')+' Bot →';
  banner.style.display='flex';
}
function updateStatus(state,mode){
  const dot=document.getElementById('status-dot');
  const text=document.getElementById('status-text');
  const actions=document.getElementById('action-btns');
  const label=mode==='audio'?'Audio Bot':'Video Avatar Bot';
  if(state==='starting'){dot.className='status-dot starting';text.innerHTML='<strong>'+label+'</strong> is starting...';actions.innerHTML='<button class="btn-stop" onclick="stopBot()">Cancel</button>';}
  else if(state==='running'){dot.className='status-dot running';text.innerHTML='<strong>'+label+'</strong> is running';actions.innerHTML='<button class="btn-stop" onclick="stopBot()">Stop</button>';}
  else{dot.className='status-dot';text.textContent='No bot running. Choose a mode above.';actions.innerHTML='';}
}
async function stopBot(){
  await fetch('/stop',{method:'POST'});
  document.getElementById('ready-banner').style.display='none';
  updateStatus(false,null);
}
fetch('/status').then(r=>r.json()).then(d=>{if(d.running)updateStatus('running',d.mode);});
</script>
</body></html>"""


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Starting Medical AI Bot on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
