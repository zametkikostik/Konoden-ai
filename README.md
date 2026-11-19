# Konoden AI — AI video editor (v0.1 skeleton)

LLM только планирует (Ollama локально или OpenRouter), всю работу делают FFmpeg и облачный Whisper.

## Быстрый старт
```bash
pip install -r requirements.txt
cp .env.example .env        # впиши OPENROUTER_API_KEY
ollama pull qwen2.5:7b-instruct
python -m konoden doctor

python -m konoden plan "Ролик 60 сек про P2P-мессенджеры" --out timeline.json
python -m konoden transcribe interview.mp4 --language ru --out transcript.json
# подставь src в timeline.json (позже это сделает модуль sources/)
python -m konoden assemble timeline.json --out draft.mp4 --audio voice.mp3
python -m konoden edl timeline.json --out cut.edl      # File > Import в Premiere
```

## White-label
Название, цвета, CLI-имя: `branding/brand.json`. Бэкенд LLM: `KONODEN_LLM_BACKEND` в `.env`.

## Дорожная карта
1. sources/ — Pexels/Pixabay, автоподстановка src
2. render/screencast — Playwright
3. render/infographic — Remotion (проверить лицензию для white-label)
4. export/xmeml — FCP7 XML для нескольких дорожек и графики
5. субтитры (burn-in) и озвучка (TTS через OpenRouter /audio/speech)
