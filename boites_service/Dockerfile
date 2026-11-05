# Service de boîtes : API et proxy de sortie. Seul conteneur à voir le socket Docker.
FROM python:3.12-slim
# Le programme docker officiel (seulement la commande, pas le démon) : plus fiable que le paquet du système.
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx pydantic
COPY boites_service /app/boites_service
EXPOSE 8080 3128
CMD ["uvicorn", "boites_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
