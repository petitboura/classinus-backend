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
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*
# nodejs et npm : requis par les outils Remotion du montage vidéo (remotion_create_project,
# remotion_render). Sans eux la passerelle les déclare indisponibles. railpack.json les
# installe déjà côté Railway, ce fichier les ajoute pour les builds Docker (staging Render).
# libatomic1 (13/11/2026) : le pilote Node de Playwright (version 1.65, requirements.txt n'épingle
# pas la version) refuse de démarrer sans elle ("libatomic.so.1: cannot open shared object file",
# code 127), ce qui faisait échouer `playwright install` et donc tout le déploiement Coolify.
# Elle doit être installée AVANT `playwright install --with-deps`, qui lance ce pilote.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Navigateur sans écran du rendu vidéo des animations (07/10/2026). En production
# Railway construit avec Railpack, pas avec ce fichier : voir docs/deployment/RAILWAY_DEPLOY.md.
RUN python -m playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
