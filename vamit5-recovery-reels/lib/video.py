"""
Salje text-to-video zahtev na Higgsfield API i ceka (polling) dok video
ne bude gotov, pa ga preuzima lokalno.

VAZNO: HIGGSFIELD_MODEL_ID mora da se podesi u GitHub Secrets. Uloguj se
na https://higgsfield.ai/create/video, isprobaj par modela sa promptom
tipa "muscular athlete performing kettlebell swing, dark cinematic
lighting, X-ray biological overlay showing glowing blood vessels and
muscle fibers" i vidi koji model_id (u API dokumentaciji/playground-u)
daje najbolji rezultat za ovaj "atleta + bioloski X-ray overlay" stil --
modeli i njihovi id-jevi se cesto dodaju/menjaju, zato NIJE fiksirano u kodu.

Auth format je "Key {api_key}:{api_key_secret}" -- oba dela dobijas kad
napravis API kljuc na platform.higgsfield.ai.
"""
import json
import os
import time
import urllib.request
import urllib.error

HIGGSFIELD_API_KEY = os.environ["HIGGSFIELD_API_KEY"].strip()
HIGGSFIELD_API_SECRET = os.environ["HIGGSFIELD_API_SECRET"].strip()
HIGGSFIELD_MODEL_ID = os.environ.get("HIGGSFIELD_MODEL_ID", "higgsfield-ai/soul/standard").strip()

BASE_URL = "https://platform.higgsfield.ai"
AUTH_HEADER = f"Key {HIGGSFIELD_API_KEY}:{HIGGSFIELD_API_SECRET}"

POLL_INTERVAL_SECONDS = 8
MAX_POLL_MINUTES = 12


def _request(method, url, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": AUTH_HEADER,
            "content-type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="ignore")
        raise RuntimeError(f"Higgsfield HTTP greska {e.code} na {url}: {error_body}") from None


def generate_video(prompt: str, out_path: str) -> str:
    submit = _request(
        "POST",
        f"{BASE_URL}/{HIGGSFIELD_MODEL_ID}",
        {
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "resolution": "1080p",
        },
    )

    if submit.get("status") == "completed":
        result = submit
    else:
        request_id = submit["request_id"]
        status_url = submit.get("status_url", f"{BASE_URL}/requests/{request_id}/status")

        deadline = time.time() + MAX_POLL_MINUTES * 60
        result = None
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            status = _request("GET", status_url)
            st = status.get("status")
            if st == "completed":
                result = status
                break
            if st in ("failed", "nsfw"):
                raise RuntimeError(f"Higgsfield generisanje nije uspelo: status={st}")
            # queued / in_progress -> nastavi da ceka

        if result is None:
            raise RuntimeError("Higgsfield generisanje je isteklo (timeout) -- probaj ponovo")

    video_url = result["video"]["url"]
    urllib.request.urlretrieve(video_url, out_path)
    return out_path
