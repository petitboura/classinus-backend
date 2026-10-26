FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-fra \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*
# nodejs et npm : requis par les outils Remotion du montage vidéo (remotion_create_project,
# remotion_render). Sans eux la passerelle les déclare indisponibles. railpack.json les
# installe déjà côté Railway, ce fichier les ajoute pour les builds Docker (staging Render).

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Navigateur sans écran du rendu vidéo des animations (07/10/2026). En production
# Railway construit avec Railpack, pas avec ce fichier : voir RAILWAY_DEPLOY.md.
RUN python -m playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
