"""
LLM Client — Gemini (primary) → Ollama fallback
=================================================

Text-only calls:
    from core.utils.llm_client import llm_generate
    text = llm_generate(prompt)
    → Gemini cascade → qwen2.5:3b

Image/PDF multimodal calls:
    from core.utils.llm_client import llm_generate_image
    text = llm_generate_image(prompt, image_bytes, mime_type='image/jpeg')
    → Gemini multimodal → gemma3:4b (via Ollama, supports vision)

Both functions return a raw string. RuntimeError only if ALL backends fail.
"""

import base64
import json
import logging
import urllib.request
import urllib.error

from google import genai

log = logging.getLogger('llm_client')

# ── LLM preference flag ───────────────────────────────────────────────────────
# Reads LLM_PREFER_LOCAL from Django settings (default False).
# When True: Ollama runs first, Gemini is skipped entirely.
def _prefer_local() -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, 'LLM_PREFER_LOCAL', False))
    except Exception:
        return False

# ── Gemini ───────────────────────────────────────────────────────────────────
import os as _os
_GEMINI_API_KEY = _os.environ.get('GEMINI_API_KEY', '')
_GEMINI_MODELS = ['gemini-3.5-flash-lite', 'gemini-3.8-flash']

# ── Ollama ───────────────────────────────────────────────────────────────────
_OLLAMA_URL = _os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/') + '/api/generate'
_OLLAMA_TEXT_MODEL = _os.environ.get('OLLAMA_TEXT_MODEL', 'qwen2.5:3b')    # text-only tasks
_OLLAMA_VISION_MODEL = _os.environ.get('OLLAMA_VISION_MODEL', 'gemma3:4b')     # image/PDF multimodal tasks
_OLLAMA_TIMEOUT = int(_os.environ.get('LLM_TIMEOUT_SECONDS', '30'))             # seconds (CPU inference can be slow)


# ── Internal helpers ─────────────────────────────────────────────────────────
def _gemini_text(prompt: str, preferred_model: str | None = None) -> str | None:
    """Try each Gemini model once (no retry). Returns text or None on failure."""
    if not _GEMINI_API_KEY:
        return None
    try:
        client = genai.Client(api_key=_GEMINI_API_KEY, http_options={'timeout': 20000})
    except Exception:
        log.warning('Gemini client could not initialize; using configured fallback.')
        return None
    models = ([preferred_model] + [m for m in _GEMINI_MODELS if m != preferred_model]
              if preferred_model else _GEMINI_MODELS)

    for model in models:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            log.debug(f'[LLM] Gemini {model} OK')
            return resp.text
        except Exception as e:
            log.warning(f'[LLM] Gemini {model} failed: {str(e)[:120]} — trying next')

    log.warning('[LLM] All Gemini models failed')
    return None


def _gemini_multimodal(prompt: str, contents: list) -> str | None:
    """Try each Gemini model once for multimodal. Returns text or None."""
    if not _GEMINI_API_KEY:
        return None
    try:
        client = genai.Client(api_key=_GEMINI_API_KEY, http_options={'timeout': 20000})
    except Exception:
        log.warning('Gemini client could not initialize; using configured fallback.')
        return None
    for model in _GEMINI_MODELS:
        try:
            resp = client.models.generate_content(model=model, contents=contents)
            log.debug(f'[LLM] Gemini multimodal {model} OK')
            return resp.text
        except Exception as e:
            log.warning(f'[LLM] Gemini multimodal {model} failed: {str(e)[:120]} — trying next')
    return None


def _ollama_text(prompt: str) -> str:
    """Call Ollama qwen2.5:3b for text. Raises on failure."""
    payload = json.dumps({
        'model':  _OLLAMA_TEXT_MODEL,
        'prompt': prompt,
        'stream': False,
    }).encode('utf-8')
    req = urllib.request.Request(
        _OLLAMA_URL, data=payload,
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(req, timeout=_OLLAMA_TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8'))['response']


def _ollama_vision(prompt: str, image_bytes: bytes) -> str:
    """
    Call Ollama gemma3:4b with an image.
    Ollama vision API: POST /api/generate with {"images": ["<base64>"]}
    """
    images = image_bytes if isinstance(image_bytes, list) else [image_bytes]
    encoded_images = [base64.b64encode(item).decode('utf-8') for item in images]
    payload = json.dumps({
        'model':  _OLLAMA_VISION_MODEL,
        'prompt': prompt,
        'images': encoded_images,
        'stream': False,
    }).encode('utf-8')
    req = urllib.request.Request(
        _OLLAMA_URL, data=payload,
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(req, timeout=_OLLAMA_TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8'))['response']


# ── Public API ────────────────────────────────────────────────────────────────
def llm_generate(prompt: str, preferred_model: str | None = None) -> str:
    """
    Text-only generation.
    Default chain : Gemini (cascade) → Ollama qwen2.5:3b → RuntimeError
    PREFER_LOCAL  : Ollama qwen2.5:3b → RuntimeError (skips Gemini)
    """
    if not _prefer_local():
        text = _gemini_text(prompt, preferred_model)
        if text:
            return text
        log.warning('[LLM] Gemini failed — falling back to Ollama qwen2.5:3b')
    else:
        log.info('[LLM] LLM_PREFER_LOCAL=True — using Ollama qwen2.5:3b directly')

    try:
        text = _ollama_text(prompt)
        log.info('[LLM] Ollama qwen2.5:3b succeeded')
        return text
    except urllib.error.URLError as e:
        raise RuntimeError(f'Ollama not reachable ({e}) — is Ollama running?')
    except Exception as e:
        raise RuntimeError(f'Ollama qwen2.5:3b failed: {e}')


def llm_generate_image(prompt: str, image_bytes: bytes,
                        mime_type: str = 'image/jpeg') -> str:
    """
    Multimodal generation (image or PDF page).
    Default chain : Gemini multimodal → Ollama gemma3:4b (vision) → RuntimeError
    PREFER_LOCAL  : Ollama gemma3:4b directly (skips Gemini)
    """
    if not _prefer_local():
        try:
            from google.genai import types as _types
            part = _types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            text = _gemini_multimodal(prompt, [prompt, part])
            if text:
                return text
        except Exception as e:
            log.warning(f'[LLM] Gemini multimodal setup failed: {e}')
        log.warning('[LLM] Gemini multimodal failed — falling back to Ollama gemma3:4b')
    else:
        log.info('[LLM] LLM_PREFER_LOCAL=True — using Ollama gemma3:4b directly')

    try:
        images = _pdf_images(image_bytes) if mime_type == 'application/pdf' else image_bytes
        text = _ollama_vision(prompt, images)
        log.info('[LLM] Ollama gemma3:4b vision succeeded')
        return text
    except urllib.error.URLError as e:
        raise RuntimeError(f'Ollama not reachable ({e}) — is Ollama running?')
    except Exception as e:
        raise RuntimeError(f'Ollama gemma3:4b failed: {e}')


# ── Health checks ─────────────────────────────────────────────────────────────
def _ollama_models() -> list[str]:
    """Return list of model names available in Ollama."""
    try:
        req = urllib.request.Request(_OLLAMA_URL.rsplit('/api/', 1)[0] + '/api/tags', method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        return [m.get('name', '') for m in data.get('models', [])]
    except Exception:
        return []


def ollama_available() -> bool:
    """True if Ollama is reachable."""
    return bool(_ollama_models())


def qwen_available() -> bool:
    """True if qwen2.5:3b is loaded in Ollama."""
    return any(_OLLAMA_TEXT_MODEL in n for n in _ollama_models())


def gemma_available() -> bool:
    """True if gemma3:4b is loaded in Ollama."""
    return any(_OLLAMA_VISION_MODEL in n for n in _ollama_models())


def _pdf_images(pdf_bytes):
    """Ollama accepts images; render each bounded PDF page rather than its bytes."""
    import io
    import pypdfium2
    images = []
    with pypdfium2.PdfDocument(pdf_bytes) as document:
        if len(document) > 20:
            raise ValueError('Use a PDF with at most 20 pages for local vision parsing.')
        for index in range(len(document)):
            page = document[index]
            try:
                scale = min(2, 1800 / max(page.get_size()))
                bitmap = page.render(scale=scale)
                try:
                    buffer = io.BytesIO()
                    bitmap.to_pil().save(buffer, format='PNG')
                    images.append(buffer.getvalue())
                finally:
                    bitmap.close()
            finally:
                page.close()
    if not images:
        raise ValueError('PDF contains no pages.')
    return images
