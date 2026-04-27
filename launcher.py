"""
Medical AI Bot - Single Process Production Server
FastAPI + LiveKit AgentServer run in same asyncio event loop via lifespan
"""

import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from livekit import api
from dotenv import load_dotenv

# ── Register plugins on main thread (required by livekit) ────────────────────
from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions
from livekit.agents.worker import AgentServer
from livekit.plugins import cartesia, deepgram, spatialreal
from livekit.plugins.openai import LLM

load_dotenv(override=True)

BOT_DIR = Path(__file__).parent
AUDIO_HTML = (BOT_DIR / "audio_ui.html").read_text(encoding="utf-8")

# ── Agent definitions ─────────────────────────────────────────────────────────

AUDIO_PROMPT = """You are Dr. Alex, a professional AI medical assistant speaking via voice.
STRICT RULES:
- Keep responses SHORT (under 15 words)
- NEVER use asterisks or action text like *smile* or *leaning*
- Speak naturally and directly, no roleplay actions
- Be warm and helpful"""

VIDEO_PROMPT = """You are Dr. Alex, a professional AI medical assistant with a 3D avatar.
STRICT RULES:
- Keep responses EXTREMELY SHORT (under 10 words)
- NEVER use asterisks or action text like *smile* or *nods*
- Speak naturally and directly, no roleplay actions
- Be warm and professional"""


class AudioAgent(Agent):
    def __init__(self):
        super().__init__(instructions=AUDIO_PROMPT)


class VideoAgent(Agent):
    def __init__(self):
        super().__init__(instructions=VIDEO_PROMPT)


async def unified_entrypoint(ctx: JobContext):
    """Single entrypoint — routes to audio or video based on room name"""
    room_name = ctx.room.name
    is_video = room_name.startswith("video-room")
    print(f"[Bot] Room: {room_name} → {'VIDEO' if is_video else 'AUDIO'} mode")

    await ctx.connect()

    llm = LLM(api_key=os.getenv("GROQ_API_KEY"),
               base_url="https://api.groq.com/openai/v1",
               model="llama-3.1-8b-instant")
    stt = deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY"))

    if is_video:
        tts = cartesia.TTS(api_key=os.getenv("CARTESIA_API_KEY"),
                           voice="694f9389-aac1-45b6-b726-9d9369183238",
                           sample_rate=24000)
        avatar = spatialreal.AvatarSession(
            api_key=os.getenv("SPATIALREAL_API_KEY"),
            app_id=os.getenv("SPATIALREAL_APP_ID"),
            avatar_id=os.getenv("SPATIALREAL_AVATAR_ID"),
            sample_rate=24000,
        )
        session = AgentSession(llm=llm, tts=tts, stt=stt)
        await avatar.start(session, room=ctx.room)
        await session.start(agent=VideoAgent(), room=ctx.room,
                            room_input_options=RoomInputOptions())
    else:
        tts = cartesia.TTS(api_key=os.getenv("CARTESIA_API_KEY"),
                           voice="694f9389-aac1-45b6-b726-9d9369183238",
                           sample_rate=16000)
        session = AgentSession(llm=llm, tts=tts, stt=stt)
        await session.start(agent=AudioAgent(), room=ctx.room,
                            room_input_options=RoomInputOptions())

    await session.generate_reply(
        instructions="Greet the user briefly and introduce yourself as Dr. Alex.")
    print(f"[Bot] Live in {'VIDEO' if is_video else 'AUDIO'} mode!")


# ── Lifespan: start both bot workers when server starts ──────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    server = AgentServer.from_server_options(WorkerOptions(
        entrypoint_fnc=unified_entrypoint,
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
        ws_url=os.getenv("LIVEKIT_URL"),
        port=8081,
        num_idle_processes=0,
    ))
    task = asyncio.create_task(server.run())
    # Swallow any task exceptions so they don't crash the lifespan
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    print("✅ Bot worker started (audio + video unified)")

    yield  # ← server runs here

    # Shutdown: cancel task, ignore CancelledError
    task.cancel()
    await asyncio.sleep(0.5)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse)
def launcher_page():
    return HTMLResponse(content=LAUNCHER_HTML)

@app.head("/")
def health_check():
    return HTMLResponse(content="", status_code=200)


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
    return JSONResponse({"running": True, "mode": "both"})


# ── HTML pages ────────────────────────────────────────────────────────────────

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
  .card{background:#0d1629;border:1.5px solid rgba(99,179,237,.12);border-radius:20px;
    padding:2rem;text-align:center;transition:all .3s;text-decoration:none;display:block;color:inherit}
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
  .btn{display:block;width:100%;padding:.85rem 1.5rem;border:none;border-radius:12px;
    font-family:'Inter',sans-serif;font-size:.95rem;font-weight:600;cursor:pointer;
    transition:all .2s;margin-top:1rem;text-align:center;text-decoration:none}
  .btn-audio{background:linear-gradient(135deg,#2563eb,#3b82f6);color:white}
  .btn-video{background:linear-gradient(135deg,#7c3aed,#8b5cf6);color:white}
  .btn:hover{transform:scale(1.03);filter:brightness(1.1)}
  .live-badge{display:inline-flex;align-items:center;gap:.4rem;background:rgba(34,197,94,.15);
    color:#4ade80;border:1px solid rgba(34,197,94,.3);padding:.3rem .8rem;
    border-radius:99px;font-size:.8rem;font-weight:600;margin-bottom:1rem}
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
  body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#f1f5f9;
    min-height:100vh;display:flex;flex-direction:column;align-items:center;
    justify-content:center;padding:1rem;overflow:hidden}
  #avatarVideo{position:fixed;top:0;left:0;width:100%;height:100%;
    object-fit:cover;z-index:0;background:#0f172a;display:none}
  .overlay{position:relative;z-index:10;width:100%;max-width:480px;
    display:flex;flex-direction:column;align-items:center;gap:1rem}
  h1{color:#a78bfa;font-size:1.8rem;font-weight:800;text-shadow:0 2px 20px rgba(0,0,0,.8)}
  .avatar-placeholder{width:160px;height:160px;border-radius:50%;
    background:linear-gradient(135deg,#7c3aed,#a78bfa);
    display:flex;align-items:center;justify-content:center;font-size:4rem;
    border:3px solid rgba(167,139,250,.4);box-shadow:0 0 40px rgba(139,92,246,.3);transition:all .3s}
  .avatar-placeholder.speaking{box-shadow:0 0 60px rgba(139,92,246,.8);border-color:#a78bfa;
    animation:avatarPulse 1s ease-in-out infinite}
  @keyframes avatarPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
  .chatbox{width:100%;max-height:180px;overflow-y:auto;
    background:rgba(15,23,42,.85);backdrop-filter:blur(10px);
    border:1px solid rgba(51,65,85,.8);border-radius:12px;
    padding:.8rem;display:flex;flex-direction:column;gap:.5rem}
  .msg{padding:.5rem .9rem;border-radius:10px;max-width:85%;font-size:.85rem;line-height:1.4}
  .bot-msg{background:rgba(51,65,85,.9);align-self:flex-start}
  .user-msg{background:rgba(124,58,237,.8);align-self:flex-end}
  .status{color:#94a3b8;font-size:.85rem;text-align:center;
    background:rgba(15,23,42,.7);padding:.4rem 1rem;border-radius:99px;backdrop-filter:blur(10px)}
  .status.listening{color:#22c55e}.status.speaking{color:#a78bfa}
  .btn{width:100%;padding:.9rem;border:none;border-radius:12px;font-size:1rem;font-weight:700;cursor:pointer;transition:.2s}
  .btn-start{background:linear-gradient(135deg,#7c3aed,#8b5cf6);color:white}
  .btn-start:hover{filter:brightness(1.1)}
  .btn-stop{background:rgba(239,68,68,.8);color:white;display:none}
  .btn:disabled{opacity:.5;cursor:not-allowed}
  .unmute{display:none;background:#f59e0b;color:#000;padding:.6rem 1rem;
    border-radius:10px;text-align:center;font-weight:700;cursor:pointer;font-size:.85rem;width:100%}
  .back{color:#475569;font-size:.8rem;text-decoration:none;margin-top:.5rem}
  .back:hover{color:#64748b}
</style>
<script src="https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.min.js"></script>
</head>
<body>
<video id="avatarVideo" autoplay playsinline></video>
<div class="overlay">
  <h1>🎬 Dr. Alex</h1>
  <div class="avatar-placeholder" id="avatarPlaceholder">🩺</div>
  <div class="chatbox" id="chatbox">
    <div class="msg bot-msg">Hello! I'm Dr. Alex. Click Start to begin.</div>
  </div>
  <div class="status" id="status">Ready</div>
  <div class="unmute" id="unmute" onclick="unmuteAll()">🔇 Click to enable audio</div>
  <button class="btn btn-start" id="startBtn" onclick="startConversation()">🎙️ Start Conversation</button>
  <button class="btn btn-stop"  id="stopBtn"  onclick="stopConversation()">⏹ Disconnect</button>
  <a class="back" href="/">← Back to launcher</a>
</div>
<script>
let room=null,audioElements=[],audioCtx=null;
const statusEl=document.getElementById('status');
const startBtn=document.getElementById('startBtn');
const stopBtn=document.getElementById('stopBtn');
const placeholder=document.getElementById('avatarPlaceholder');
const avatarVideo=document.getElementById('avatarVideo');
const chatbox=document.getElementById('chatbox');
const unmuteEl=document.getElementById('unmute');

function setStatus(txt,cls){statusEl.textContent=txt;statusEl.className='status '+(cls||'');}
function getOrUpdateMsg(id,text,isUser){
  let el=document.getElementById('msg_'+id);
  if(!el){el=document.createElement('div');el.id='msg_'+id;
    el.className='msg '+(isUser?'user-msg':'bot-msg');chatbox.appendChild(el);}
  el.textContent=text;chatbox.scrollTop=chatbox.scrollHeight;
}
function unmuteAll(){
  if(audioCtx&&audioCtx.state==='suspended')audioCtx.resume();
  audioElements.forEach(el=>{el.muted=false;el.volume=1.0;el.play().catch(()=>{});});
  unmuteEl.style.display='none';
}
async function startConversation(){
  startBtn.disabled=true;setStatus('Connecting...');
  try{
    audioCtx=new(window.AudioContext||window.webkitAudioContext)();
    const roomName='video-room-'+Math.random().toString(36).substring(2,9);
    const res=await fetch('/token',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({room:roomName,mode:'video',participant_name:'User'})});
    const data=await res.json();
    if(!data.token||!data.url)throw new Error('Token failed: '+JSON.stringify(data));
    room=new LivekitClient.Room({
      adaptiveStream: false,
      dynacast: false,
    });
    room.on(LivekitClient.RoomEvent.TrackSubscribed,(track,pub,participant)=>{
      console.log('TRACK SUBSCRIBED kind='+track.kind+' from='+participant.identity+' source='+pub.source);
      if(track.kind===LivekitClient.Track.Kind.Audio){
        const el=track.attach();
        el.autoplay=true;el.muted=false;el.volume=1.0;
        document.body.appendChild(el);audioElements.push(el);
        el.play().catch(()=>{unmuteEl.style.display='block';});
      }
      if(track.kind===LivekitClient.Track.Kind.Video){
        console.log('VIDEO TRACK! attaching...');
        const el = track.attach();
        el.autoplay=true;
        el.playsInline=true;
        el.muted=true;
        el.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:1;background:#000';
        document.body.appendChild(el);
        placeholder.style.display='none';
        el.play().catch(e=>console.warn('video play err:',e));
      }
    });
    room.on(LivekitClient.RoomEvent.TrackPublished,(pub,participant)=>{
      console.log('TRACK PUBLISHED kind='+pub.kind+' from='+participant.identity+' subscribed='+pub.isSubscribed);
    });
    room.on(LivekitClient.RoomEvent.ParticipantConnected,(p)=>{
      console.log('Participant connected:',p.identity,'tracks:',p.trackPublications.size);
      if(p.identity.startsWith('agent'))setStatus('🤖 Dr. Alex joined!','listening');
      p.trackPublications.forEach((pub,sid)=>{
        console.log('  existing track:',pub.kind,'subscribed:',pub.isSubscribed,'source:',pub.source);
      });
    });
    room.on(LivekitClient.RoomEvent.TrackUnsubscribed,(track)=>{
      track.detach();
      if(track.kind===LivekitClient.Track.Kind.Video){
        avatarVideo.style.display='none';placeholder.style.display='flex';}
    });
    room.on(LivekitClient.RoomEvent.ActiveSpeakersChanged,(speakers)=>{
      const agentSpeaking=speakers.some(s=>s.identity.startsWith('agent'));
      const userSpeaking=speakers.some(s=>s.identity==='User');
      if(agentSpeaking){placeholder.classList.add('speaking');setStatus('🔊 Dr. Alex is speaking...','speaking');}
      else if(userSpeaking){placeholder.classList.remove('speaking');setStatus('🎤 Listening...','listening');}
      else{placeholder.classList.remove('speaking');setStatus('💬 Speak to Dr. Alex...');}
    });
    room.on(LivekitClient.RoomEvent.TranscriptionReceived,(segments,participant)=>{
      // participant null = local user's own speech
      // participant with 'agent' identity = bot
      const isAgent=participant!=null&&participant.identity.startsWith('agent');
      for(const seg of segments){
        if(seg.text&&seg.text.trim())getOrUpdateMsg(seg.id,seg.text,!isAgent);
      }
    });
    room.on(LivekitClient.RoomEvent.Disconnected,()=>{setStatus('Disconnected');resetUI();});
    await room.connect(data.url,data.token);
    // Check already-connected participants for existing video tracks
    room.remoteParticipants.forEach((p)=>{
      console.log('Already connected:',p.identity);
      p.trackPublications.forEach((pub)=>{
        console.log('  track:',pub.kind,'subscribed:',pub.isSubscribed);
        if(pub.isSubscribed && pub.track){
          if(pub.track.kind===LivekitClient.Track.Kind.Video){
            console.log('Attaching existing video track from',p.identity);
            pub.track.attach(avatarVideo);
            avatarVideo.muted=true;
            avatarVideo.style.display='block';
            placeholder.style.display='none';
            avatarVideo.play().catch(e=>console.warn('Video play:',e));
          }
          if(pub.track.kind===LivekitClient.Track.Kind.Audio){
            const el=pub.track.attach();
            el.autoplay=true;el.muted=false;el.volume=1.0;
            document.body.appendChild(el);audioElements.push(el);
            el.play().catch(()=>{unmuteEl.style.display='block';});
          }
        }
      });
    });
    await room.localParticipant.setMicrophoneEnabled(true);
    setStatus('⏳ Waiting for Dr. Alex...');
    startBtn.style.display='none';stopBtn.style.display='block';
  }catch(e){console.error(e);setStatus('❌ '+e.message);startBtn.disabled=false;}
}
async function stopConversation(){
  if(room){await room.disconnect();room=null;}
  audioElements.forEach(el=>{el.pause();el.remove();});audioElements=[];
  if(audioCtx){audioCtx.close();audioCtx=null;}
  resetUI();
}
function resetUI(){
  startBtn.style.display='block';startBtn.disabled=false;
  stopBtn.style.display='none';avatarVideo.style.display='none';
  placeholder.style.display='flex';placeholder.classList.remove('speaking');
  unmuteEl.style.display='none';setStatus('Ready');
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Starting Medical AI Bot on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
