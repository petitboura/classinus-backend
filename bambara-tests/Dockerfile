FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/data/hf
WORKDIR /app
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
COPY static ./static
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
