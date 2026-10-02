# 1. Menggunakan basis Python resmi Linux yang stabil
FROM python:3.12-slim

# 2. Instal FFmpeg, Node.js (untuk JS Runtime yt-dlp), dan alat kompilasi suara
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    build-essential \
    libopus-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Tentukan folder kerja di dalam server
WORKDIR /app

# 4. Copy file requirements dan instal library Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy seluruh sisa file bot ke dalam server
COPY . .

# 6. Jalankan bot musik kamu
CMD ["python", "bot.py"]
