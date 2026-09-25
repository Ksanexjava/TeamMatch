FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Сначала только зависимости — Docker кэширует этот слой, пересборка кода быстрая
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Не запускаем бота от root
RUN useradd --create-home appuser
USER appuser

CMD ["python", "-m", "bot.main"]
