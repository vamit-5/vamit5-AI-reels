"""
Pretvara tekst naracije u audio fajl koristeci ElevenLabs API
(Eleven Multilingual v2 model, podrzava srpski).

VOICE_ID mora biti dubok muski glas -- podesi u GitHub Secrets
(ELEVENLABS_VOICE_ID). Predlog: u ElevenLabs Voice Library pretrazi
"deep" + "male" + isprobaj sa srpskim tekstom pre nego sto odaberes,
zvuci se dosta razlikuju po jeziku iako je model isti.
"""
import os
import time
import urllib.request
import urllib.error

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
VOICE_ID = os.environ["ELEVENLABS_VOICE_ID"]

MAX_RETRIES = 5


def synthesize(text: str, out_path: str) -> str:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.8,
            "style": 0.35,
            "use_speaker_boost": True,
        },
    }
    import json
    body = json.dumps(payload).encode("utf-8")

    delay = 5
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "content-type": "application/json",
                "accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio_bytes = resp.read()
            with open(out_path, "wb") as f:
                f.write(audio_bytes)
            return out_path
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise RuntimeError(f"ElevenLabs trajna greska {e.code}: {e.read().decode(errors='ignore')}")
            last_err = e
        except urllib.error.URLError as e:
            last_err = e

        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"ElevenLabs TTS nije uspeo posle {MAX_RETRIES} pokusaja: {last_err}")
