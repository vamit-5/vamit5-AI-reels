"""
Objavljuje Reels na Instagram preko Meta Graph API, u dva koraka:
1. Kreira media container (REELS, video_url, caption)
2. Ceka da Instagram obradi video (status_code=FINISHED), pa publish-uje

Isti retry princip kao ostatak sistema: 5 pokusaja sa rastucom pauzom,
samo za privremene (mrezne/5xx) greske.
"""
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse

ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_USER_ID = os.environ["IG_BUSINESS_ACCOUNT_ID"]

GRAPH_BASE = "https://graph.instagram.com/v21.0"
MAX_RETRIES = 5
MAX_PROCESSING_WAIT_MINUTES = 10


def _post(url, params):
    delay = 5
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(params).encode("utf-8"), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")
            if 400 <= e.code < 500:
                raise RuntimeError(f"Instagram trajna greska {e.code}: {body}")
            last_err = e
        except urllib.error.URLError as e:
            last_err = e
        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Instagram poziv nije uspeo posle {MAX_RETRIES} pokusaja: {last_err}")


def _get(url, params):
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def publish_reel(video_url: str, caption: str) -> str:
    create = _post(f"{GRAPH_BASE}/{IG_USER_ID}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN,
    })
    container_id = create["id"]

    deadline = time.time() + MAX_PROCESSING_WAIT_MINUTES * 60
    while time.time() < deadline:
        status = _get(f"{GRAPH_BASE}/{container_id}", {
            "fields": "status_code,status",
            "access_token": ACCESS_TOKEN,
        })
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            # pokusaj da izvucemo JOS detalja (Meta ponekad vrati opsirniji
            # opis greske preko debug_token/graph error endpoint-a)
            try:
                debug = _get(f"{GRAPH_BASE}/{container_id}", {
                    "fields": "status_code,status,copyright_check_information",
                    "access_token": ACCESS_TOKEN,
                })
            except Exception:
                debug = status
            raise RuntimeError(f"Instagram obrada videa nije uspela: {debug}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram obrada videa je istekla (timeout)")

    publish = _post(f"{GRAPH_BASE}/{IG_USER_ID}/media_publish", {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    })
    return publish["id"]
