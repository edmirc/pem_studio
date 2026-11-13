# ---------- Etapa 1: compila as dependências (mysqlclient precisa de gcc) ----------
FROM python:3.12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------- Etapa 2: imagem final, só com o necessário ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Cuiaba \
    MEDIA_ROOT=/app/media
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmariadb3 tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

WORKDIR /app
COPY --chown=app:app . .
# Arquivos estáticos (CSS, JS, admin) gerados dentro da imagem
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput -v0 \
    && mkdir -p /app/media && chown app:app /app/media
USER app

EXPOSE 8000
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
