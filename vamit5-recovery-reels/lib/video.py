"""
Dvokorakno generisanje video epizode preko Higgsfield Cloud API-ja:
1. Higgsfield Soul (text-to-image) generise sliku atlete iz teksta
2. Higgsfield DoP Lite (image-to-video) animira tu sliku u kratak pokret

Auth: dva odvojena header-a "hf-api-key" i "hf-secret" (potvrdjeno iz
stvarnog Playground cURL primera na cloud.higgsfield.ai).
"""
import json
import os
import time
import urllib.request
import urllib.error

HIGGSFIELD_API_KEY = os.environ["HIGGSFIELD_API_KEY"].strip()
HIGGSFIELD_API_SECRET = os.environ["HIGGSFIELD_API_SECRET"].strip()

SOUL_URL = "https://platform.higgsfield.ai/v1/text2image/soul"
DOP_LITE_URL = "https://platform.higgsfield.ai/higgsfield-ai/dop/lite"

POLL_INTERVAL_SECONDS = 8
MAX_POLL_MINUTES = 12


def _headers():
    return {
        "Content-Type": "application/json",
        "hf-api-key": HIGGSFIELD_API_KEY,
        "hf-secret": HIGGSFIELD_API_SECRET,
        "Accept": "application/json",
        # Cloudflare (ispred Higgsfield API-ja) blokira podrazumevani
        # "Python-urllib" User-Agent kao bota (error code 1010) -- ovo to
        # zaobilazi predstavljajuci se kao obican browser
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }


def _post(url, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="ignore")
        raise RuntimeError(f"Higgsfield HTTP greska {e.code} na {url}: {error_body}") from None


def _get(url):
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="ignore")
        raise RuntimeError(f"Higgsfield HTTP greska {e.code} na {url}: {error_body}") from None


def _wait_for_completion(submit_response):
    if submit_response.get("status") == "completed":
        return submit_response

    request_id = submit_response.get("request_id")
    status_url = submit_response.get("status_url") or (
        f"https://platform.higgsfield.ai/requests/{request_id}/status" if request_id else None
    )
    if not status_url:
        return submit_response

    deadline = time.time() + MAX_POLL_MINUTES * 60
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status = _get(status_url)
        st = status.get("status")
        if st == "completed":
            return status
        if st in ("failed", "nsfw"):
            raise RuntimeError(f"Higgsfield generisanje nije uspelo: status={st}")
    raise RuntimeError("Higgsfield generisanje je isteklo (timeout) -- probaj ponovo")


def _extract_url(result, *candidate_paths):
    for path in candidate_paths:
        node = result
        try:
            for key in path:
                node = node[key]
            if isinstance(node, str) and node.startswith("http"):
                return node
        except (KeyError, IndexError, TypeError):
            continue
    raise RuntimeError(f"Nisam nasao URL rezultata u Higgsfield odgovoru: {result}")


def generate_episode_video(image_prompt: str, video_prompt: str, out_path: str) -> str:
    submit_image = _post(SOUL_URL, {
        "params": {
            "prompt": image_prompt,
            "quality": "1080p",
            "batch_size": 1,
            "enhance_prompt": True,
            "style_strength": 1,
            "width_and_height": "1536x1536",
        }
    })
    image_result = _wait_for_completion(submit_image)
    image_url = _extract_url(
        image_result,
        ("images", 0, "url"),
        ("image", "url"),
        ("output", "url"),
    )

    submit_video = _post(DOP_LITE_URL, {
        "prompt": video_prompt,
        "motions": [],
        "image_url": image_url,
        "enhance_prompt": True,
    })
    video_result = _wait_for_completion(submit_video)
    video_url = _extract_url(
        video_result,
        ("video", "url"),
        ("videos", 0, "url"),
        ("output", "url"),
    )

    urllib.request.urlretrieve(video_url, out_path)
    return out_path
