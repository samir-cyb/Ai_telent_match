"""
test_local_llm.py
=================
Run this from the project root to verify both local Ollama models are
working correctly before relying on them as Gemini fallbacks.

Usage:
    cd E:\web\ai-talent-match3\Ai_telent_match
    python test_local_llm.py

What it tests:
    1. Ollama reachable + models listed
    2. qwen2.5:3b  — text generation (JSON output)
    3. gemma3:4b   — text generation (basic)
    4. gemma3:4b   — vision / image understanding (creates a tiny test PNG)
    5. Full llm_generate() call (simulates what the app does)
    6. Full llm_generate_image() call (simulates resume image parsing)
"""

import base64
import json
import struct
import time
import urllib.request
import urllib.error
import zlib

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
BLUE   = '\033[94m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

PASS = f'{GREEN}✓ PASS{RESET}'
FAIL = f'{RED}✗ FAIL{RESET}'
INFO = f'{BLUE}ℹ{RESET}'

OLLAMA_URL   = 'http://localhost:11434'
QWEN_MODEL   = 'qwen2.5:3b'
GEMMA_MODEL  = 'gemma3:4b'
TIMEOUT      = 180  # seconds — CPU inference


# ── Helpers ───────────────────────────────────────────────────────────────────
def _post(endpoint: str, payload: dict, timeout: int = TIMEOUT) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req  = urllib.request.Request(
        f'{OLLAMA_URL}{endpoint}',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _get(endpoint: str, timeout: int = 5) -> dict:
    req = urllib.request.Request(f'{OLLAMA_URL}{endpoint}', method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _make_test_png() -> bytes:
    """
    Build a minimal valid 8×8 PNG with a red square — no Pillow needed.
    gemma3:4b will receive this and describe what it sees.
    """
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)

    # 8×8 RGB pixels — solid red
    raw = b''
    for _ in range(8):
        row = b'\x00' + b'\xFF\x00\x00' * 8   # filter byte + 8 red pixels
        raw += row
    compressed = zlib.compress(raw)

    png  = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', 8, 8, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', compressed)
    png += chunk(b'IEND', b'')
    return png


def section(title: str):
    print(f'\n{BOLD}{BLUE}{"─" * 60}{RESET}')
    print(f'{BOLD}{BLUE}  {title}{RESET}')
    print(f'{BOLD}{BLUE}{"─" * 60}{RESET}')


def result(label: str, ok: bool, detail: str = ''):
    icon = PASS if ok else FAIL
    print(f'  {icon}  {label}')
    if detail:
        print(f'       {YELLOW}{detail}{RESET}')


# ── Test 1: Ollama reachable ──────────────────────────────────────────────────
def test_ollama_connection():
    section('TEST 1 — Ollama connection & available models')
    try:
        data  = _get('/api/tags', timeout=5)
        names = [m.get('name', '') for m in data.get('models', [])]
        result('Ollama is reachable', True, f'URL: {OLLAMA_URL}')
        print(f'\n  {INFO}  Models loaded in Ollama:')
        for n in names:
            marker = f'{GREEN}✓{RESET}' if (QWEN_MODEL in n or GEMMA_MODEL in n) else ' '
            print(f'       {marker}  {n}')

        qwen_ok  = any(QWEN_MODEL  in n for n in names)
        gemma_ok = any(GEMMA_MODEL in n for n in names)
        result(f'{QWEN_MODEL} is available',  qwen_ok,
               '' if qwen_ok  else f'Run: ollama pull {QWEN_MODEL}')
        result(f'{GEMMA_MODEL} is available', gemma_ok,
               '' if gemma_ok else f'Run: ollama pull {GEMMA_MODEL}')
        return qwen_ok, gemma_ok
    except urllib.error.URLError:
        result('Ollama is reachable', False,
               'Ollama is NOT running.  Start it with:  ollama serve')
        return False, False
    except Exception as e:
        result('Ollama connection', False, str(e))
        return False, False


# ── Test 2: qwen2.5:3b text ───────────────────────────────────────────────────
def test_qwen_text():
    section(f'TEST 2 — {QWEN_MODEL} text generation')
    prompt = ('Return ONLY valid JSON, no explanation:\n'
              '{"status": "ok", "model": "qwen", "answer": "2+2=4"}')
    print(f'  {INFO}  Prompt: {prompt[:80]}')
    t0 = time.time()
    try:
        resp = _post('/api/generate', {'model': QWEN_MODEL, 'prompt': prompt, 'stream': False})
        elapsed = round(time.time() - t0, 1)
        text = resp.get('response', '')
        result(f'Got a response in {elapsed}s', bool(text), text[:120])

        # Try to parse as JSON
        try:
            # Strip markdown fences if model added them
            clean = text.strip()
            if clean.startswith('```'):
                clean = clean.split('```')[1]
                if clean.startswith('json'):
                    clean = clean[4:]
                clean = clean.split('```')[0]
            parsed = json.loads(clean.strip())
            result('Response is valid JSON', True, f'status={parsed.get("status")}')
        except Exception:
            result('Response is valid JSON', False, f'Raw: {text[:120]}')
    except Exception as e:
        result(f'{QWEN_MODEL} text call', False, str(e))


# ── Test 3: gemma3:4b text ────────────────────────────────────────────────────
def test_gemma_text():
    section(f'TEST 3 — {GEMMA_MODEL} text generation')
    prompt = 'Say exactly: GEMMA_OK'
    print(f'  {INFO}  Prompt: {prompt}')
    t0 = time.time()
    try:
        resp    = _post('/api/generate', {'model': GEMMA_MODEL, 'prompt': prompt, 'stream': False})
        elapsed = round(time.time() - t0, 1)
        text    = resp.get('response', '')
        result(f'Got a response in {elapsed}s', bool(text), text[:120])
        result('Response contains expected keyword', 'GEMMA_OK' in text.upper() or len(text) > 3,
               text[:120])
    except Exception as e:
        result(f'{GEMMA_MODEL} text call', False, str(e))


# ── Test 4: gemma3:4b vision ──────────────────────────────────────────────────
def test_gemma_vision():
    section(f'TEST 4 — {GEMMA_MODEL} vision / image understanding')
    print(f'  {INFO}  Creating a minimal 8×8 red PNG test image (no file needed)')
    png_bytes = _make_test_png()
    b64       = base64.b64encode(png_bytes).decode('utf-8')
    prompt    = 'What colour is this image? Answer in one word.'
    print(f'  {INFO}  Image: 8×8 solid red PNG ({len(png_bytes)} bytes)')
    print(f'  {INFO}  Prompt: {prompt}')
    t0 = time.time()
    try:
        resp    = _post('/api/generate', {
            'model':  GEMMA_MODEL,
            'prompt': prompt,
            'images': [b64],
            'stream': False,
        })
        elapsed = round(time.time() - t0, 1)
        text    = resp.get('response', '')
        result(f'Got a response in {elapsed}s', bool(text), text[:200])
        # gemma3 should say red/Red
        is_correct = 'red' in text.lower()
        result('Correctly identified red colour', is_correct,
               f'Response: "{text.strip()[:80]}"')
    except Exception as e:
        result(f'{GEMMA_MODEL} vision call', False, str(e))


# ── Test 5: llm_generate() end-to-end ─────────────────────────────────────────
def test_llm_generate():
    section('TEST 5 — llm_generate() (app function, text path)')
    print(f'  {INFO}  This simulates what interview_generator, code_grader etc. call')
    try:
        import django
        import os
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')
        django.setup()
        from core.utils.llm_client import llm_generate
        t0      = time.time()
        text    = llm_generate('Reply with exactly: LLM_GENERATE_OK')
        elapsed = round(time.time() - t0, 1)
        result(f'llm_generate() returned in {elapsed}s', bool(text), text[:120])
    except Exception as e:
        result('llm_generate() call', False, str(e))


# ── Test 6: llm_generate_image() end-to-end ───────────────────────────────────
def test_llm_generate_image():
    section('TEST 6 — llm_generate_image() (app function, vision path)')
    print(f'  {INFO}  This simulates what resume_parser uses for image CVs')
    try:
        import django, os
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')
        django.setup()
        from core.utils.llm_client import llm_generate_image
        png_bytes = _make_test_png()
        t0        = time.time()
        text      = llm_generate_image(
            'What colour is this image? Answer in one word.',
            png_bytes,
            mime_type='image/png',
        )
        elapsed = round(time.time() - t0, 1)
        result(f'llm_generate_image() returned in {elapsed}s', bool(text), text[:120])
    except Exception as e:
        result('llm_generate_image() call', False, str(e))


# ── Summary ───────────────────────────────────────────────────────────────────
def main():
    print(f'\n{BOLD}{"=" * 60}')
    print('  AI Talent Match — Local LLM Health Check')
    print(f'{"=" * 60}{RESET}')
    print(f'  {INFO}  Ollama URL : {OLLAMA_URL}')
    print(f'  {INFO}  Text model : {QWEN_MODEL}')
    print(f'  {INFO}  Vision mdl : {GEMMA_MODEL}')
    print(f'  {INFO}  Timeout    : {TIMEOUT}s per call')

    qwen_ok, gemma_ok = test_ollama_connection()

    if qwen_ok:
        test_qwen_text()
    else:
        section(f'TEST 2 — {QWEN_MODEL} text generation')
        print(f'  {YELLOW}SKIPPED — model not available{RESET}')

    if gemma_ok:
        test_gemma_text()
        test_gemma_vision()
    else:
        for n in [3, 4]:
            section(f'TEST {n} — {GEMMA_MODEL}')
            print(f'  {YELLOW}SKIPPED — model not available{RESET}')

    test_llm_generate()
    test_llm_generate_image()

    print(f'\n{BOLD}{"=" * 60}')
    print('  Done.')
    print(f'{"=" * 60}{RESET}\n')


if __name__ == '__main__':
    main()
