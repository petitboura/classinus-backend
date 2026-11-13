FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# NeMo 2.6.2 impose lhotse 1.31.1, incompatible avec le torch récent (Sampler sans data_source).
# La 1.33.0 corrige ce point exact; installée à part car le résolveur refuserait le conflit.
RUN pip install --no-cache-dir --no-deps lhotse==1.33.0

COPY app.py index.html ./

ENV HF_HOME=/models
ENV MODEL_NAME=RobotsMali/soloni-114m-tdt-ctc-v3
ENV PORT=8000

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
