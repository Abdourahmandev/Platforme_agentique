"""Loopback-only speech endpoint for the Telegram bridge."""
import hmac
import os
import tempfile
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from faster_whisper import WhisperModel
import uvicorn

ROOT = Path(__file__).resolve().parent
TOKEN = os.environ["TELEGRAM_STT_SECRET"]
recognizer = WhisperModel(str(ROOT / "model-base"), device="cpu", compute_type="int8", cpu_threads=4)
lock = Lock()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health():
    return {"healthy": True, "model": "base", "device": "cpu", "compute_type": "int8"}


@app.post("/v1/audio/transcriptions")
def transcribe(file: UploadFile = File(...), model: str = Form("base"), language: str = Form(""), authorization: str = Header("")):
    if not hmac.compare_digest(authorization, "Bearer " + TOKEN):
        raise HTTPException(401, "Unauthorized")
    if not lock.acquire(blocking=False):
        raise HTTPException(429, "Speech recognizer is busy; please try again shortly")
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as temporary:
            path = Path(temporary.name)
            total = 0
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > 20 * 1024 * 1024:
                    raise HTTPException(413, "Voice note exceeds 20 MB")
                temporary.write(chunk)
        segments, info = recognizer.transcribe(str(path), language=language or None, beam_size=3, vad_filter=True, condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return {"text": text, "language": info.language}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "The voice note could not be transcribed") from None
    finally:
        if path:
            path.unlink(missing_ok=True)
        file.file.close()
        lock.release()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=4123, access_log=False)
