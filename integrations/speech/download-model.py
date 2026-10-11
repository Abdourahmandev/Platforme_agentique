import json
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download
from faster_whisper import WhisperModel

root = Path(__file__).resolve().parent
repo = "Systran/faster-whisper-base"
revision = HfApi().model_info(repo).sha
snapshot_download(repo, revision=revision, local_dir=root / "model-base", allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
model = WhisperModel(str(root / "model-base"), device="cpu", compute_type="int8", cpu_threads=4)
result = {"repository": repo, "revision": revision, "device": "cpu", "compute_type": "int8", "loaded": True}
(root / "model-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
