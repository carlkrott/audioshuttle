"""Gemma 4 E4B native multimodal audio transcription engine.

Converts audio to mel-spectrogram images and sends them to the E4B model
for high-speed, domain-aware transcription.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import librosa
    import numpy as np
    from PIL import Image
    _MULTIMODAL_READY = True
except ImportError:
    _MULTIMODAL_READY = False


class GemmaAudioEngine:
    """Uses E4B multimodal capabilities to 'hear' and transcribe audio."""

    def __init__(self, model_server: Any) -> None:
        self._model_server = model_server

    @property
    def is_available(self) -> bool:
        return _MULTIMODAL_READY and self._model_server is not None and self._model_server.is_running

    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio via E4B multimodal turn."""
        if not self.is_available:
            return ""

        try:
            # 1. Load audio and convert to spectrogram
            y, sr = librosa.load(audio_path, sr=16000, duration=30.0)
            S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=8000)
            S_db = librosa.power_to_db(S, ref=np.max)
            
            # Normalize to 0-255
            S_norm = ((S_db - S_db.min()) * (255 / (S_db.max() - S_db.min() + 1e-6))).astype(np.uint8)
            img = Image.fromarray(S_norm[::-1])
            
            # 2. Encode to Base64
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            
            # 3. Send to E4B
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "This image is a mel-spectrogram of a user speaking a DAW command. Listen carefully and transcribe the EXACT words spoken. Do not add any preamble."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    ]
                }
            ]
            
            result = self._model_server.chat_multimodal(messages, temperature=0.1)
            if result:
                text = result.strip()
                logger.info("E4B Transcribed: %s", text)
                return text
                
        except Exception as e:
            logger.error("GemmaAudioEngine failed: %s", e)
            
        return ""
