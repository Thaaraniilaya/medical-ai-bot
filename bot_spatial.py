"""
SpatialReal Video Avatar Bot
- LLM: Groq (llama-3.1-8b-instant) - FREE
- TTS: Cartesia - clear voice
- STT: Deepgram - accurate transcription
- Avatar: SpatialReal (your avatar ID)
- Transport: LiveKit
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv(override=True)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

print("Starting SpatialReal Video Avatar Bot...")

from livekit import api
from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions, cli
from livekit.plugins import cartesia, deepgram, silero, spatialreal, openai
from livekit.plugins.openai import LLM as OpenAICompatLLM

SYSTEM_PROMPT = """You are Dr. Alex, a warm and professional AI medical assistant. 
IMPORTANT: Keep your responses EXTREMELY SHORT (under 10 words).
Always respond in English. You are speaking as a male 3D avatar doctor."""

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
    print("CRITICAL ERROR: Missing LiveKit credentials in .env!")
    sys.exit(1)


class MedicalAvatarAgent(Agent):
    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)

async def entrypoint(ctx: JobContext):
    print(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()

    # Groq LLM (free, fast)
    llm = OpenAICompatLLM(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
    )

    # Cartesia TTS (ULTRA FAST) - Must be 24000 for SpatialReal Lip Sync!
    tts = cartesia.TTS(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice="694f9389-aac1-45b6-b726-9d9369183238", # Baritone Male
        sample_rate=24000,
    )

    # Deepgram STT (accurate)
    stt = deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # Silero VAD (Optimized for no false interruptions)
    vad = silero.VAD.load(
        min_silence_duration=0.6,
    )

    # SpatialReal Avatar
    avatar = spatialreal.AvatarSession(
        api_key=os.getenv("SPATIALREAL_API_KEY"),
        app_id=os.getenv("SPATIALREAL_APP_ID"),
        avatar_id=os.getenv("SPATIALREAL_AVATAR_ID"),
        sample_rate=24000,
    )

    session = AgentSession(
        llm=llm,
        tts=tts,
        stt=stt,
        vad=vad,
        allow_interruptions=False,
    )

    @session.on("user_started_speaking")
    def _user_start():
        print(f"[{time.time()}] 🎤 User started speaking...")

    @session.on("user_stopped_speaking")
    def _user_stop():
        print(f"[{time.time()}] 🤔 User stopped speaking, thinking...")

    @session.on("user_speech_committed")
    def _user_speech(transcript):
        print(f"[{time.time()}] 💬 User said: {transcript}")

    @session.on("agent_started_speaking")
    def _agent_start():
        print(f"[{time.time()}] 🔊 Dr. Alex is speaking...")

    print("Starting Avatar and Session...")
    # Start SpatialReal avatar (MUST be before session.start to hook events)
    await avatar.start(session, room=ctx.room)

    # Start the voice agent
    await session.start(
        agent=MedicalAvatarAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )

    # Greet the user
    await session.generate_reply(
        instructions="Greet the user warmly and introduce yourself as Dr. Alex."
    )
    print("Dr. Alex is live!")


if __name__ == "__main__":
    print("Starting SpatialReal Avatar Worker...")
    print(f"LiveKit URL: {LIVEKIT_URL}")

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
