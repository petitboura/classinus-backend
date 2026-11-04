# Service de boîtes : API et proxy de sortie. Seul conteneur à voir le socket Docker.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx pydantic
COPY boites_service /app/boites_service
EXPOSE 8080 3128
CMD ["uvicorn", "boites_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
