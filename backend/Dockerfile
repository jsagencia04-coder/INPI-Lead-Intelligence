# API e worker usam a mesma imagem. Construir a partir da raiz do repositório:
#   docker build -f backend/Dockerfile -t inpi-backend .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir . && useradd -m app && mkdir -p data && chown app data
# app/migrate.py procura as migrations em ../../supabase/migrations
COPY supabase/migrations /srv/supabase/migrations
USER app
EXPOSE 8000
# Worker: docker run ... inpi-backend python -m app.worker
CMD ["sh", "-c", "python -m app.migrate && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
