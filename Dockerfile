FROM python:3.11-slim

WORKDIR /app

# System deps for audio processing
RUN apt-get update && apt-get install -y \
    gcc \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY launcher.py .
COPY bot_audio_livekit_fixed.py .
COPY bot_spatial.py .
COPY audio_ui.html .

EXPOSE 8080

CMD ["python", "launcher.py"]
