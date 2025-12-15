# 1. Берем за основу легкий Linux с Python 3.10
FROM python:3.10-slim

# 2. Устанавливаем системные утилиты и FFmpeg (Одной строкой!)
# Это та магия, ради которой мы ставим Docker. Не нужно мучиться с Windows PATH.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 3. Создаем рабочую папку внутри контейнера
WORKDIR /app

# 4. Копируем файл с библиотеками
COPY requirements.txt .

# 5. Устанавливаем библиотеки Python
RUN pip install --no-cache-dir -r requirements.txt

# 6. Копируем весь остальной код проекта внутрь
COPY . .

# 7. Говорим Докеру, какой порт открыть (Streamlit работает на 8501)
EXPOSE 8501

# 8. Команда для запуска приложения
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]