# backend/shazam_helper.py
from shazamio import Shazam


async def recognize_music(file_path: str):
    """
    Принимает путь к файлу (mp3/m4a/mp4), отправляет его в Shazam.
    Возвращает строку: "Title - Artist" или None.
    """
    try:
        shazam = Shazam()
        # Shazam анализирует файл
        out = await shazam.recognize(file_path)

        # Проверяем, нашлось ли что-то
        if "track" in out:
            track = out["track"]
            title = track.get("title", "Unknown Title")
            subtitle = track.get("subtitle", "Unknown Artist")
            return f"{title} - {subtitle}"

        return None
    except Exception as e:
        print(f"Shazam error: {e}")
        return None
