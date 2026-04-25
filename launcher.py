"""
Launcher server for the Medical AI Bot.
Run this with: uv run launcher.py
Then open: http://localhost:8080
"""

import os
import sys
import time
import socket
import subprocess
import signal
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from livekit import api

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

bot_process = None
frontend_process = None
current_mode = None
ENV_FILE = Path(__file__).parent / ".env"
BOT_DIR = Path(__file__).parent
FRONTEND_DIR = Path(__file__).parent  # Not used in production
AUDIO_HTML = (BOT_DIR / "audio_ui.html").read_text(encoding="utf-8")



def read_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def write_env_key(key: str, value: str):
    lines = ENV_FILE.read_text().splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(new_lines))


def kill_process_on_port(port):
    try:
        if sys.platform == "win32":
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
                    time.sleep(0.5) # Wait for port release

    except Exception:
        pass

def kill_bot():
    """Stop the currently running bot"""
    global bot_process, frontend_process
    
    # 1. Kill tracked processes cleanly using taskkill /T to prevent memory leaks from child workers
    if bot_process and bot_process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(bot_process.pid)], capture_output=True)
        else:
            bot_process.terminate()
    bot_process = None
    
    if frontend_process and frontend_process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(frontend_process.pid)], capture_output=True)
        else:
            frontend_process.terminate()
    frontend_process = None

    # 2. Force clear ports (in case of zombies)
    kill_process_on_port(7861)
    kill_process_on_port(3000)
    kill_process_on_port(7860)
    kill_process_on_port(8081)


@app.get("/", response_class=HTMLResponse)
def launcher_page():
    return HTMLResponse(content=LAUNCHER_HTML)


@app.get("/audio", response_class=HTMLResponse)
def audio_playground():
    return HTMLResponse(content=AUDIO_HTML)


@app.post("/start/{mode}")
def start_bot(mode: str):
    global bot_process, frontend_process, current_mode

    if mode not in ("audio", "video"):
        return JSONResponse({"error": "Invalid mode"}, status_code=400)

    kill_bot()
    time.sleep(1.5) # Extra time for port release on Windows

    python_path = str(BOT_DIR / ".venv" / "Scripts" / "python.exe")
    if mode == "audio":
        bot_script = [python_path, "bot_audio_livekit_fixed.py", "start"]
    else:
        bot_script = [python_path, "bot_spatial.py", "start"]

    bot_process = subprocess.Popen(
        bot_script,
        cwd=str(BOT_DIR),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )

    if mode == "video":
        frontend_process = subprocess.Popen(
            "npm run dev",
            cwd=str(FRONTEND_DIR),
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )

    current_mode = mode
    return JSONResponse({"status": "started", "mode": mode})


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

    # Also accept mode from query param
    mode_qp = request.query_params.get("mode", mode)
    if mode_qp == "audio" and not room_name.startswith("audio-room"):
        room_name = "audio-room-" + room_name

    env = read_env()
    api_key = env.get("LIVEKIT_API_KEY")
    api_secret = env.get("LIVEKIT_API_SECRET")
    livekit_url = env.get("LIVEKIT_URL")
    
    if not api_key or not api_secret or not livekit_url:
        return JSONResponse({"error": "Missing LiveKit credentials in .env"}, status_code=500)
        
    token = api.AccessToken(api_key, api_secret) \
        .with_identity(participant_name) \
        .with_name(participant_name) \
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
        )).to_jwt()
        
    return JSONResponse({
        "token": token,
        "url": livekit_url,
        "room": room_name
    })

@app.post("/stop")
def stop_bot():
    global current_mode
    kill_bot()
    current_mode = None
    return JSONResponse({"status": "stopped"})


@app.get("/status")
def bot_status():
    global current_mode
    running = current_mode is not None
    return JSONResponse({"running": running, "mode": current_mode})


@app.get("/check-port/{port}")
def check_port_ready(port: int):
    """Server-side port check — bypasses browser CORS restrictions completely."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return JSONResponse({"ready": True})
    except Exception:
        pass
    
    try:
        with socket.create_connection(("::1", port), timeout=0.5):
            return JSONResponse({"ready": True})
    except Exception:
        return JSONResponse({"ready": False})


LAUNCHER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Medical AI Bot Launcher</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #050b18;
    --card: #0d1629;
    --border: rgba(99, 179, 237, 0.12);
    --accent-blue: #3b82f6;
    --accent-purple: #8b5cf6;
    --accent-teal: #14b8a6;
    --text: #e2e8f0;
    --muted: #64748b;
  }

  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    background-image:
      radial-gradient(ellipse at 20% 20%, rgba(59,130,246,0.08) 0%, transparent 50%),
      radial-gradient(ellipse at 80% 80%, rgba(139,92,246,0.08) 0%, transparent 50%);
  }

  .logo {
    font-size: 2.8rem;
    margin-bottom: 0.5rem;
    filter: drop-shadow(0 0 20px rgba(59,130,246,0.5));
  }

  h1 {
    font-size: 2.2rem;
    font-weight: 800;
    background: linear-gradient(135deg, #60a5fa, #a78bfa, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.4rem;
    text-align: center;
  }

  .subtitle {
    color: var(--muted);
    font-size: 1rem;
    margin-bottom: 3rem;
    text-align: center;
  }

  .cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    width: 100%;
    max-width: 700px;
    margin-bottom: 2rem;
  }

  .card {
    background: var(--card);
    border: 1.5px solid var(--border);
    border-radius: 20px;
    padding: 2rem;
    cursor: pointer;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
    text-align: center;
  }

  .card::before {
    content: '';
    position: absolute;
    inset: 0;
    opacity: 0;
    transition: opacity 0.3s;
    border-radius: 20px;
  }

  .card.audio::before { background: radial-gradient(ellipse at top, rgba(59,130,246,0.15), transparent 70%); }
  .card.video::before { background: radial-gradient(ellipse at top, rgba(139,92,246,0.15), transparent 70%); }

  .card:hover { transform: translateY(-4px); border-color: rgba(99,179,237,0.3); }
  .card:hover::before { opacity: 1; }
  .card.audio:hover { border-color: rgba(59,130,246,0.5); box-shadow: 0 20px 60px rgba(59,130,246,0.15); }
  .card.video:hover { border-color: rgba(139,92,246,0.5); box-shadow: 0 20px 60px rgba(139,92,246,0.15); }

  .card-icon { font-size: 3rem; margin-bottom: 1rem; display: block; }
  .card-title { font-size: 1.3rem; font-weight: 700; margin-bottom: 0.5rem; }
  .card.audio .card-title { color: #60a5fa; }
  .card.video .card-title { color: #a78bfa; }
  .card-desc { color: var(--muted); font-size: 0.875rem; line-height: 1.6; margin-bottom: 1.5rem; }

  .tag {
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 99px;
    font-size: 0.75rem;
    font-weight: 600;
    margin: 0.2rem;
  }
  .tag-blue { background: rgba(59,130,246,0.15); color: #60a5fa; }
  .tag-purple { background: rgba(139,92,246,0.15); color: #a78bfa; }
  .tag-teal { background: rgba(20,184,166,0.15); color: #34d399; }

  .btn {
    width: 100%;
    padding: 0.85rem 1.5rem;
    border: none;
    border-radius: 12px;
    font-family: 'Inter', sans-serif;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
    margin-top: 1rem;
  }

  .btn-audio {
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    color: white;
  }
  .btn-video {
    background: linear-gradient(135deg, #7c3aed, #8b5cf6);
    color: white;
  }
  .btn:hover { transform: scale(1.03); filter: brightness(1.1); }
  .btn:active { transform: scale(0.98); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

  .status-bar {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.5rem;
    width: 100%;
    max-width: 700px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .status-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--muted);
    transition: background 0.3s;
    flex-shrink: 0;
  }
  .status-dot.running { background: #22c55e; box-shadow: 0 0 8px #22c55e; animation: pulse 2s infinite; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .status-text { font-size: 0.875rem; color: var(--muted); flex: 1; }
  .status-text strong { color: var(--text); }

  .btn-stop {
    background: rgba(239,68,68,0.15);
    color: #f87171;
    border: 1px solid rgba(239,68,68,0.3);
    padding: 0.4rem 1rem;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-family: 'Inter', sans-serif;
  }
  .btn-stop:hover { background: rgba(239,68,68,0.25); }

  .open-btn {
    background: rgba(34,197,94,0.15);
    color: #4ade80;
    border: 1px solid rgba(34,197,94,0.3);
    padding: 0.4rem 1rem;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-family: 'Inter', sans-serif;
    text-decoration: none;
  }
  .open-btn:hover { background: rgba(34,197,94,0.25); }

  .loading { display: none; }
  .loading.show { display: inline-block; }
  .spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: 6px;
    vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Ready Banner */
  .ready-banner {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    background: linear-gradient(135deg, rgba(34,197,94,0.12), rgba(20,184,166,0.08));
    border: 1.5px solid rgba(34,197,94,0.4);
    border-radius: 16px;
    padding: 1.2rem 1.8rem;
    width: 100%;
    max-width: 700px;
    margin-bottom: 1rem;
    animation: bannerAppear 0.4s ease;
  }
  @keyframes bannerAppear {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .ready-banner .ready-text {
    font-size: 0.95rem;
    color: #86efac;
    font-weight: 600;
  }
  .ready-banner .ready-text span {
    color: #4ade80;
    font-size: 1.3rem;
    margin-right: 0.5rem;
  }
  .open-now-btn {
    display: inline-block;
    padding: 0.75rem 1.8rem;
    background: linear-gradient(135deg, #16a34a, #22c55e);
    color: white;
    font-family: 'Inter', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    border-radius: 12px;
    text-decoration: none;
    border: none;
    cursor: pointer;
    box-shadow: 0 0 20px rgba(34,197,94,0.4);
    transition: all 0.2s ease;
    white-space: nowrap;
  }
  .open-now-btn:hover {
    transform: scale(1.05);
    box-shadow: 0 0 30px rgba(34,197,94,0.6);
  }

  /* Status states */
  .status-dot.starting { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; animation: pulse 1s infinite; }
  .status-dot.running  { background: #22c55e; box-shadow: 0 0 8px #22c55e; animation: pulse 2s infinite; }
</style>
</head>
<body>

<div class="logo">Medical</div>
<h1>Medical AI Bot</h1>
<p class="subtitle">Choose your interaction mode to get started</p>

<div class="cards">
  <div class="card audio" onclick="startBot('audio')">
    <span class="card-icon">Audio</span>
    <div class="card-title">Audio Bot</div>
    <p class="card-desc">Voice-only interaction. Fast, lightweight, and perfect for quick consultations.</p>
    <div>
      <span class="tag tag-blue">Deepgram STT</span>
      <span class="tag tag-teal">Cartesia TTS</span>
      <span class="tag tag-blue">Groq LLM</span>
    </div>
    <button class="btn btn-audio" id="btn-audio">
      <span class="loading" id="load-audio"><span class="spinner"></span></span>
      Start Audio Bot
    </button>
  </div>

  <div class="card video" onclick="startBot('video')">
    <span class="card-icon">Video</span>
    <div class="card-title">Video Avatar Bot</div>
    <p class="card-desc">Live 3D avatar with lip-sync powered by SpatialReal. Speak to Dr. Aria face-to-face.</p>
    <div>
      <span class="tag tag-purple">SpatialReal Avatar</span>
      <span class="tag tag-teal">Cartesia TTS</span>
      <span class="tag tag-purple">Groq LLM</span>
    </div>
    <button class="btn btn-video" id="btn-video">
      <span class="loading" id="load-video"><span class="spinner"></span></span>
      Start Video Bot
    </button>
  </div>
</div>

<div class="status-bar">
  <div class="status-dot" id="status-dot"></div>
  <div class="status-text" id="status-text">No bot running. Choose a mode above.</div>
  <div id="action-btns" style="display:flex;gap:0.5rem;"></div>
</div>

<!-- Ready Banner: appears when bot is fully started -->
<div class="ready-banner" id="ready-banner">
  <div class="ready-text"><span>✅</span> Bot is ready! Click to open:</div>
  <a class="open-now-btn" id="ready-link" href="#" target="_blank">Open Bot →</a>
</div>

<script>
  let pollInterval = null;
  let currentBotUrl = null;

  async function startBot(mode) {
    const btnId = mode === 'audio' ? 'btn-audio' : 'btn-video';
    const loadId = mode === 'audio' ? 'load-audio' : 'load-video';
    const btn = document.getElementById(btnId);
    const load = document.getElementById(loadId);
    const port = mode === 'audio' ? 8081 : 3000;
    const url = mode === 'video' ? 'http://localhost:3000' : 'http://localhost:8080/audio';

    btn.disabled = true;
    load.classList.add('show');
    btn.childNodes[btn.childNodes.length - 1].textContent = ' Starting...';

    // Stop any previous polling
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }

    try {
      const res = await fetch(`/start/${mode}`, { method: 'POST' });
      const data = await res.json();

      if (data.status === 'started') {
        currentBotUrl = url;
        updateStatus('starting', mode, url);

        // Wait 10 seconds for LiveKit python worker to fully boot up before opening UI
        setTimeout(() => {
          updateStatus('running', mode, url);
          showReadyBanner(url, mode);
        }, 10000);
      }

    } catch (e) {
      alert('Failed to start bot: ' + e.message);
    } finally {
      btn.disabled = false;
      load.classList.remove('show');
      btn.childNodes[btn.childNodes.length - 1].textContent = mode === 'audio' ? ' Start Audio Bot' : ' Start Video Bot';
    }
  }

  function showReadyBanner(url, mode) {
    const label = mode === 'video' ? 'Video Avatar Bot' : 'Audio Bot';
    const banner = document.getElementById('ready-banner');
    const bannerLink = document.getElementById('ready-link');
    bannerLink.href = url;
    bannerLink.textContent = `Open ${label} →`;
    banner.style.display = 'flex';
    // Auto-scroll to banner
    banner.scrollIntoView({ behavior: 'smooth' });
  }

  async function stopBot() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    await fetch('/stop', { method: 'POST' });
    document.getElementById('ready-banner').style.display = 'none';
    updateStatus(false, null, null);
  }

  function updateStatus(state, mode, url) {
    // state: false | 'starting' | 'running'
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const actions = document.getElementById('action-btns');

    if (state === 'starting') {
      dot.className = 'status-dot starting';
      const label = mode === 'video' ? 'Video Avatar Bot' : 'Audio Bot';
      text.innerHTML = `<strong>${label}</strong> is starting up... <small style="color:#f59e0b">(please wait)</small>`;
      actions.innerHTML = `<button class="btn-stop" onclick="stopBot()">Cancel</button>`;
    } else if (state === 'running') {
      dot.className = 'status-dot running';
      const label = mode === 'video' ? 'Video Avatar Bot' : 'Audio Bot';
      const actualUrl = url || (mode === 'video' ? 'http://localhost:3000' : 'http://localhost:8080/audio');
      text.innerHTML = `<strong>${label}</strong> is running — click the green button above`;
      actions.innerHTML = `
        <a class="open-btn" href="${actualUrl}" target="_blank">Open</a>
        <button class="btn-stop" onclick="stopBot()">Stop</button>
      `;
    } else {
      dot.className = 'status-dot';
      text.textContent = 'No bot running. Choose a mode above.';
      actions.innerHTML = '';
    }
  }

  // Background poll — only update if we're NOT in a starting/polling state
  async function pollStatus() {
    if (pollInterval) return; // Don't override active polling
    try {
      const res = await fetch('/status');
      const data = await res.json();
      if (!pollInterval) { // Double-check after await
        updateStatus(data.running ? 'running' : false, data.mode);
      }
    } catch (e) {}
  }

  pollStatus();
  setInterval(pollStatus, 3000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("Starting Medical AI Bot Launcher")
    print("Open http://localhost:8080 in your browser")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
