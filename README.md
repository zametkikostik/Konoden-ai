# Konoden AI — AI video editor

LLM только планирует (Ollama локально или OpenRouter). Всю работу делают
FFmpeg, облачный Whisper (OpenRouter) и сток-API. Бренд настраивается для white-label.

## Быстрый старт
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,screencast]"
playwright install chromium
cp .env.example .env            # ключи: OPENROUTER_API_KEY, PEXELS_API_KEY и/или PIXABAY_API_KEY
ollama pull qwen2.5:7b-instruct
konoden doctor
```

## Пайплайн
```bash
konoden plan "Ролик 60 сек про P2P-мессенджеры" --out timeline.json   # бриф -> таймлайн
konoden resolve timeline.json                                          # подбор и скачивание стока
konoden swap timeline.json c03 --pick 2                                # заменить материал на альтернативу
konoden screencast examples/screencast_demo.json --out demo.mp4        # скринкаст с курсором и зумом
konoden render timeline.json                                           # записать screencast-клипы по их scenario
konoden transcribe interview.mp4 --language ru                         # облачный Whisper
konoden assemble timeline.json --out draft.mp4 --audio voice.mp3       # черновик
konoden edl timeline.json --out cut.edl                                # File > Import в Premiere Pro
```

## Структура
```
konoden/
  core/      схема таймлайна (контракт между модулями)
  llm/       адаптеры Ollama / OpenRouter
  stt/       транскрипция через OpenRouter
  sources/   Pexels / Pixabay, ранжирование, кэш, swap
  render/    FFmpeg-сборка, скринкасты (Playwright)
  export/    EDL для Premiere
branding/    brand.json — белая этикетка
examples/    пример сценария скринкаста
tests/       pytest (20 тестов; браузерные пропускаются, если нет Chromium)
```

## Известные ограничения
- STT OpenRouter отдаёт текст без таймкодов: тайминг на уровне куска.
- EDL: одна видеодорожка, только склейки.
- Pexels/Pixabay: перед коммерческим white-label проверить условия API (требования к указанию источника). Атрибуция сохраняется в `clip.attribution`.
- Провайдеры стока проверены только на заглушках, живыми ключами пока нет.

## Скринкасты: формат сценария
Шаги: `goto`, `click`, `type`, `press`, `hover`, `scroll`, `zoom`, `wait`. Курсор и «рябь» при клике рисуются оверлеем.
`allowed_hosts` ограничивает, куда сценарий (особенно сгенерированный LLM) может ходить.
Ограничения: после `zoom` курсор не масштабируется вместе с контентом (делай zoom на финальной цели или сбрасывай перед кликами);
zoom использует transform на `<body>`, страницы с `position: fixed` могут вести себя странно.

## Дорожная карта
- [x] v0.1 каркас: схема, LLM, STT, сборка, EDL
- [x] v0.2 sources: подбор стока + swap
- [x] v0.3 screencast (Playwright)
- [ ] v0.4 infographic (Remotion; проверить лицензию)
- [ ] v0.5 export xmeml (несколько дорожек), субтитры, TTS
