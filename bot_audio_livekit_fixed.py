"""
AUDIO-ONLY BOT - PROFESSIONAL VERSION WITH FIXED AUDIO
- LLM: Groq (llama-3.1-8b-instant) - FREE
- TTS: Cartesia - ultra-clear voice
- STT: Deepgram - accurate transcription
- Transport: LiveKit WebRTC (enterprise-grade, AUDIO FULLY FIXED)
- No Avatar - Pure audio conversation
"""

import os
import sys
import time
from dotenv import load_dotenv

# ==================== SETUP ====================
load_dotenv(override=True)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

print("\n" + "="*60)
print("🎙️  AUDIO BOT - PURE VOICE CONVERSATION")
print("="*60)

# ==================== IMPORTS ====================
from livekit import api
from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions, cli
from livekit.plugins import cartesia, deepgram, silero, openai
from livekit.plugins.openai import LLM as OpenAICompatLLM

# ==================== CONFIGURATION ====================
SYSTEM_PROMPT = """You are Dr. Alex, a warm, professional AI medical assistant.
CRITICAL RULES:
- Keep responses SHORT (5-15 words maximum)
- Respond INSTANTLY without delays
- Be friendly, clear, and helpful
- Speak as if talking to a patient"""

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# ==================== VALIDATION ====================
required_vars = [
    ("LIVEKIT_URL", LIVEKIT_URL),
    ("LIVEKIT_API_KEY", LIVEKIT_API_KEY),
    ("LIVEKIT_API_SECRET", LIVEKIT_API_SECRET),
    ("GROQ_API_KEY", os.getenv("GROQ_API_KEY")),
    ("CARTESIA_API_KEY", os.getenv("CARTESIA_API_KEY")),
    ("DEEPGRAM_API_KEY", os.getenv("DEEPGRAM_API_KEY")),
]

missing = [name for name, value in required_vars if not value]
if missing:
    print(f"\n❌ ERROR: Missing environment variables: {', '.join(missing)}")
    print("✅ Please check your .env file\n")
    sys.exit(1)

print("✅ All environment variables loaded successfully\n")

# ==================== AGENT CLASS ====================
class MedicalAudioAgent(Agent):
    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)

# ==================== MAIN ENTRYPOINT ====================
async def entrypoint(ctx: JobContext):
    print(f"\n🔗 Connecting to LiveKit room: {ctx.room.name}")
    await ctx.connect()
    print("✅ Connected to LiveKit room!\n")

    # ========== LLM (Groq - Fast & Free) ==========
    print("⚙️  Initializing LLM (Groq Llama 3.1)...")
    llm = OpenAICompatLLM(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
    )
    print("✅ LLM ready\n")

    # ========== TTS (Cartesia - Crystal Clear) ==========
    print("⚙️  Initializing TTS (Cartesia)...")
    tts = cartesia.TTS(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice="694f9389-aac1-45b6-b726-9d9369183238",  # Male doctor voice
        sample_rate=16000,
    )
    print("✅ TTS ready\n")

    # ========== STT (Deepgram - Accurate) ==========
    print("⚙️  Initializing STT (Deepgram)...")
    stt = deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY"))
    print("✅ STT ready\n")

    # ========== VAD (Silero - Optimized) ==========
    print("⚙️  Initializing VAD (Silero)...")
    vad = silero.VAD.load(
        min_silence_duration=0.6,
    )
    print("✅ VAD ready\n")

    # ========== SESSION ==========
    print("⚙️  Creating Audio Session...")
    session = AgentSession(
        llm=llm,
        tts=tts,
        stt=stt,
        vad=vad,
        allow_interruptions=False,
    )
    print("✅ Session created\n")

    # ========== EVENT HANDLERS ==========
    @session.on("user_started_speaking")
    def _user_start():
        print(f"[{time.time():.1f}] 🎤 User is speaking...")

    @session.on("user_stopped_speaking")
    def _user_stop():
        print(f"[{time.time():.1f}] 🤔 Dr. Alex is thinking...")

    @session.on("user_speech_committed")
    def _user_speech(transcript):
        print(f"[{time.time():.1f}] 💬 User: {transcript}")

    @session.on("agent_started_speaking")
    def _agent_start():
        print(f"[{time.time():.1f}] 🔊 Dr. Alex is speaking...")

    @session.on("agent_stopped_speaking")
    def _agent_stop():
        print(f"[{time.time():.1f}] ✅ Dr. Alex finished speaking")

    # ========== START SESSION ==========
    print("🚀 Starting Audio Agent Session...\n")
    await session.start(
        agent=MedicalAudioAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )
    print("✅ Audio session started!\n")

    # ========== GREETING ==========
    print("💬 Sending greeting message to user...\n")
    await session.generate_reply(
        instructions="Greet the user warmly and introduce yourself as Dr. Alex, your AI medical assistant. Keep it very short."
    )

    print("\n" + "="*60)
    print("✨ DR. ALEX AUDIO BOT IS LIVE! ✨")
    print("="*60)
    print("Your AI doctor is ready to help!")
    print("="*60 + "\n")

# ==================== MAIN ====================
if __name__ == "__main__":
    print("🎙️  Starting Audio-Only Bot Worker...")
    print(f"📍 LiveKit Server: {LIVEKIT_URL}\n")

    # Inject 'start' subcommand so livekit runs in production mode (no file watcher)
    if len(sys.argv) == 1:
        sys.argv.append("start")

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
            ws_url=LIVEKIT_URL,
            load_threshold=1.0,
        )
    )
