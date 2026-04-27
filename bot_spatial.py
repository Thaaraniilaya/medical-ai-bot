"""
SpatialReal Video Avatar Bot - No Silero VAD (too slow on CPU)
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

from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions, cli
from livekit.plugins import cartesia, deepgram, spatialreal
from livekit.plugins.openai import LLM as OpenAICompatLLM

SYSTEM_PROMPT = """You are Dr. Alex, a professional AI medical assistant with a 3D avatar.
STRICT RULES:
- Keep responses EXTREMELY SHORT (under 10 words)
- NEVER use asterisks or action text like *smile* or *nods*
- Speak naturally and directly
- Be warm and professional"""

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

    llm = OpenAICompatLLM(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.1-8b-instant",
    )

    # Must be 24000 for SpatialReal lip sync
    tts = cartesia.TTS(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice="694f9389-aac1-45b6-b726-9d9369183238",
        sample_rate=24000,
    )

    stt = deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # NO silero VAD — too slow on CPU, causes avatar timeout
    session = AgentSession(
        llm=llm,
        tts=tts,
        stt=stt,
        allow_interruptions=False,
    )

    avatar = spatialreal.AvatarSession(
        api_key=os.getenv("SPATIALREAL_API_KEY"),
        app_id=os.getenv("SPATIALREAL_APP_ID"),
        avatar_id=os.getenv("SPATIALREAL_AVATAR_ID"),
        sample_rate=24000,
    )

    @session.on("user_speech_committed")
    def _user_speech(transcript):
        print(f"[{time.time():.1f}] User: {transcript}")

    @session.on("agent_started_speaking")
    def _agent_start():
        print(f"[{time.time():.1f}] Dr. Alex speaking...")

    print("Starting Avatar and Session...")
    await avatar.start(session, room=ctx.room)

    await session.start(
        agent=MedicalAvatarAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )

    await session.generate_reply(
        instructions="Greet the user briefly as Dr. Alex. No action text."
    )
    print("Dr. Alex is live!")


if __name__ == "__main__":
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
