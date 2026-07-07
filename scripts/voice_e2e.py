"""End-to-end test of the deployed voice app, driven by a list of user utterances.

Launches a real browser against the app's test mode (?text=1) and plays a full
shopping conversation. Each utterance goes in either as typed text or as audio
(synthesized via OpenAI TTS and injected into the WebRTC mic track, so server
VAD + transcription handle it exactly like real speech). Exercises the whole
stack: browser → OpenAI Realtime → voice backend → superstore MCP server →
PC Express.

The conversation is model-driven, so assertions are structural: a cart item
appears, and the final cart link carries a forced cart id.

Usage:
    uv run python scripts/voice_e2e.py                     # default journey, text in
    uv run python scripts/voice_e2e.py --mode audio        # same journey, audio in (needs OPENAI_API_KEY)
    uv run python scripts/voice_e2e.py --headed            # watch it run
    uv run python scripts/voice_e2e.py --url http://localhost:8000
    uv run python scripts/voice_e2e.py --script my_convo.json
    uv run python scripts/voice_e2e.py "I'm at V5K 0A1" "First one please" \
        "Add 2 percent milk" "audio:clips/done.wav"

Utterance forms:
    "plain text"        → typed text (text mode) or TTS-synthesized audio (audio mode)
    "audio:path.wav"    → always injected as audio from the given file

Script file: a JSON list of utterance strings, or {"utterances": [...]}.
"""

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

DEFAULT_URL = "https://dbandrews--voice-shopping-ui.modal.run"

# Default journey: set store → pick store → add item → finish.
DEFAULT_UTTERANCES = [
    "I'm at T2N 1A1 in Calgary.",
    "The first one works, thanks.",
    "Please add a bunch of bananas to my cart.",
    "That's everything, I'm done. Thanks!",
]

TTS_CACHE_DIR = Path.home() / ".cache" / "voice-e2e-tts"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "alloy"


def load_env_key(name: str) -> str | None:
    """Return env var, falling back to the repo .env file."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def synthesize_tts(text: str) -> bytes:
    """Text → WAV bytes via OpenAI TTS, cached on disk."""
    import httpx

    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{TTS_MODEL}:{TTS_VOICE}:{text}".encode()).hexdigest()
    cached = TTS_CACHE_DIR / f"{key}.wav"
    if cached.exists():
        return cached.read_bytes()

    api_key = load_env_key("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required for --mode audio (env or .env)")
    resp = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": TTS_MODEL,
            "voice": TTS_VOICE,
            "input": text,
            "response_format": "wav",
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    cached.write_bytes(resp.content)
    return resp.content


def transcript(page: Page) -> list[tuple[str, str]]:
    """All transcript messages as (role, text)."""
    out = []
    for el in page.locator("#transcript .msg").all():
        role = (el.get_attribute("class") or "").replace("msg", "").strip()
        out.append((role, el.inner_text().strip()))
    return out


def dump_transcript(page: Page) -> None:
    print("      --- transcript ---")
    for role, text in transcript(page):
        print(f"      [{role:9s}] {text}")
    print("      ------------------")


def check_for_errors(page: Page) -> None:
    for role, text in transcript(page):
        if role == "system" and text.lower().startswith("error"):
            dump_transcript(page)
            raise RuntimeError(f"App reported error: {text}")


def status(page: Page) -> dict:
    return page.evaluate("() => (window.__voiceStatus ? window.__voiceStatus() : {})")


def settle(page: Page, prev_count: int, timeout_s: float = 120) -> str:
    """Wait for the turn to fully finish: a new assistant message exists AND the
    session is idle (no active response, no tool call in flight). This spans any
    spoken filler + backend/MCP round-trip, so the reply we return is the final
    one for the turn, not an interim "let me check"."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        check_for_errors(page)
        st = status(page)
        msgs = page.locator("#transcript .msg.assistant").all_inner_texts()
        idle = not st.get("responseActive") and not st.get("toolCallsInFlight")
        if len(msgs) > prev_count and msgs[-1].strip() and idle:
            # Confirm it stays idle briefly (not a momentary gap between responses).
            time.sleep(1.5)
            st2 = status(page)
            if not st2.get("responseActive") and not st2.get("toolCallsInFlight"):
                return page.locator("#transcript .msg.assistant").all_inner_texts()[-1].strip()
        time.sleep(0.8)
    dump_transcript(page)
    raise TimeoutError(f"Turn did not settle after {timeout_s}s")


def send_text(page: Page, text: str) -> int:
    """Type a user message; returns assistant-message count before sending."""
    count = page.locator("#transcript .msg.assistant").count()
    print(f">>    {text}")
    page.fill("#text-input", text)
    page.press("#text-input", "Enter")
    return count


def send_audio(page: Page, wav_bytes: bytes, label: str) -> int:
    """Inject audio into the fake mic track; returns prior assistant count."""
    count = page.locator("#transcript .msg.assistant").count()
    user_count = page.locator("#transcript .msg.user").count()
    print(f">>    [audio] {label}")
    b64 = base64.b64encode(wav_bytes).decode()
    before = page.evaluate("() => window.__rtcStats()")
    duration = page.evaluate("b64 => window.__playAudioBase64(b64)", b64)
    print(f"      -> playing {duration:.1f}s of audio into the mic track")
    # Wait out the clip plus VAD close (500ms silence) before polling.
    time.sleep(duration + 1.5)
    after = page.evaluate("() => window.__rtcStats()")
    st = status(page)
    print(
        f"      -> rtc: ctx={after.get('audioCtxState')} "
        f"energy {before.get('totalAudioEnergy')}->{after.get('totalAudioEnergy')} "
        f"packets {before.get('packetsSent')}->{after.get('packetsSent')} "
        f"vadStarts={st.get('speechStartedCount')}"
    )
    # The user transcript is our proof VAD + transcription heard the clip.
    deadline = time.time() + 30
    while time.time() < deadline:
        check_for_errors(page)
        if page.locator("#transcript .msg.user").count() > user_count:
            heard = page.locator("#transcript .msg.user").all_inner_texts()[-1].strip()
            print(f'      -> transcribed as: "{heard}"')
            return count
        time.sleep(0.8)
    dump_transcript(page)
    raise TimeoutError(f"No user transcript within 30s of playing audio ({label})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("utterances", nargs="*", help="User utterances (default: full journey)")
    parser.add_argument("--script", help="JSON file with a list of utterances")
    parser.add_argument("--mode", default="text", choices=["text", "audio"],
                        help="How plain-text utterances go in: typed text or TTS audio")
    parser.add_argument("--url", default=DEFAULT_URL, help="Voice app base URL")
    parser.add_argument("--headed", action="store_true", help="Show the browser")
    parser.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    parser.add_argument("--ws", action="store_true",
                        help="Force the WebSocket transport (?ws=1; Firefox uses it automatically)")
    args = parser.parse_args()

    if args.script:
        data = json.loads(Path(args.script).read_text())
        utterances = data["utterances"] if isinstance(data, dict) else data
    elif args.utterances:
        utterances = args.utterances
    else:
        utterances = DEFAULT_UTTERANCES

    # Pre-synthesize audio so TTS latency doesn't eat into turn timeouts.
    audio_clips: dict[int, tuple[bytes, str]] = {}
    for i, utt in enumerate(utterances):
        if utt.startswith("audio:"):
            path = Path(utt[len("audio:"):])
            audio_clips[i] = (path.read_bytes(), path.name)
        elif args.mode == "audio":
            print(f"[tts] synthesizing: {utt!r}")
            audio_clips[i] = (synthesize_tts(utt), utt)

    total = len(utterances)
    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch(
            headless=not args.headed,
            args=["--autoplay-policy=no-user-gesture-required"] if args.browser == "chromium" else [],
        )
        page = browser.new_page()
        page.on(
            "console",
            lambda msg: msg.type in ("error", "warning") and print(f"      [console] {msg.text[:200]}"),
        )

        query = "?text=1" + ("&ws=1" if args.ws else "")
        print(f"[0/{total}] open {args.url}/{query} and start session")
        page.goto(f"{args.url}/{query}")
        page.click("#start-btn")
        page.wait_for_selector("#text-composer.active", timeout=45_000)
        print("      -> Realtime data channel open (test mode)")

        greeting = settle(page, 0, timeout_s=60)
        print(f"<<    {greeting}")

        for i, utt in enumerate(utterances):
            is_last = i == total - 1
            print(f"[{i + 1}/{total}]")
            if i in audio_clips:
                wav, label = audio_clips[i]
                n = send_audio(page, wav, label)
            else:
                n = send_text(page, utt)
            if is_last:
                # Final turn: the model should call finish_shopping, which
                # reveals the cart link (no assistant transcript is guaranteed
                # after the goodbye, so wait on the link itself).
                page.wait_for_selector("#cart-link", state="visible", timeout=90_000)
            else:
                reply = settle(page, n, timeout_s=120)
                print(f"<<    {reply}")

        cart_items = page.locator("#cart-items li").all_inner_texts()
        cart_href = page.get_attribute("#cart-link-a", "href") or ""
        final_status = status(page)
        print(f"      -> cart UI shows: {cart_items}")
        print(f"      -> cart link: {cart_href}")

        dump_transcript(page)
        browser.close()

        if "forceCartId" not in cart_href:
            print(f"FAIL: cart link has no forced cart id: {cart_href}")
            return 1
        if not cart_items:
            print("FAIL: no cart items rendered")
            return 1
        if not final_status.get("cartId"):
            print(f"FAIL: no cart id in app state: {final_status}")
            return 1
        print(f"\nPASS ({args.mode} mode): browser → Realtime → backend → MCP → PCX loop works")
        return 0


if __name__ == "__main__":
    sys.exit(main())
