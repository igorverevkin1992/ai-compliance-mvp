# Используем легкий образ Python
FROM python:3.10-slim

# 1. ВАЖНО: Устанавливаем FFmpeg и git на уровне системы
# Без этого subprocess.run(["ffmpeg", ...]) выдаст ошибку "File not found"
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# 2. Копируем requirements и устанавливаем зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Копируем весь код
COPY . .

# Открываем порт и запускаем приложение
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]