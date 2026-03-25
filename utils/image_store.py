from __future__ import annotations

from datetime import datetime
from pathlib import Path
import uuid


def save_image_bytes(image_bytes: bytes, image_dir: str | Path | None = None) -> str:
    target_dir = Path(image_dir) if image_dir is not None else Path(__file__).resolve().parents[1] / "images"
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    image_path = target_dir / f"generated_image_{timestamp}_{unique_id}.png"
    image_path.write_bytes(image_bytes)
    return str(image_path)
