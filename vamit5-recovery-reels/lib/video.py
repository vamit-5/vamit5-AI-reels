"""
Dvokorakno generisanje video epizode preko Higgsfield Cloud API-ja:
1. Higgsfield Soul (text-to-image) generise sliku atlete iz teksta
2. Higgsfield DoP Lite (image-to-video) animira tu sliku u kratak pokret

Auth: dva odvojena header-a "hf-api-key" i "hf-secret".
Odgovori imaju ugnjezdenu strukturu: {"id":..., "jobs":[{"id":..., "status":...,
"results": [...]}]} -- pravi ID za pracenje statusa je jobs[0]["id"], ne
spoljni "id".
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
STATUS_URL_TMPL = "https://platform.higgsfield.ai/requests/{request_id}/status"

POLL_INTERVAL_SECONDS = 8
MAX_POLL_MINUTES = 12


def _headers():
    return {
        "Content-Type": "application/json",
        "hf-api-key": HIGGSFIELD_API_KEY,
        "hf-secret": HIGGSFIELD_API_SECRET,
        "Accept": "application/json",
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


def _job(resp):
    """Higgsfield odgovori umotavaju stvarni posao u jobs[0]."""
    jobs = resp.get("jobs")
    if jobs:
        return jobs[0]
    return resp


def _wait_for_job(submit_response):
    job = _job(submit_response)
    if job.get("status") == "completed":
        return job

    request_id = job.get("id")
    if not request_id:
        raise RuntimeError(f"Nema request_id u Higgsfield odgovoru: {submit_response}")
    status_url = STATUS_URL_TMPL.format(request_id=request_id)

    deadline = time.time() + MAX_POLL_MINUTES * 60
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status_resp = _get(status_url)
        job = _job(status_resp)
        st = job.get("status")
        if st == "completed":
            return job
        if st in ("failed", "nsfw", "error"):
            raise RuntimeError(f"Higgsfield generisanje nije uspelo: {job}")
    raise RuntimeError("Higgsfield generisanje je isteklo (timeout) -- probaj ponovo")


def _extract_url_from_job(job):
    results = job.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            for key in ("url", "image_url", "video_url"):
                if isinstance(first.get(key), str):
                    return first[key]
    if isinstance(results, dict):
        for key in ("url", "image_url", "video_url"):
            if isinstance(results.get(key), str):
                return results[key]
    for key in ("url", "output_url"):
        if isinstance(job.get(key), str):
            return job[key]
    raise RuntimeError(f"Nisam nasao URL rezultata u zavrsenom poslu: {job}")


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
    image_job = _wait_for_job(submit_image)
    image_url = _extract_url_from_job(image_job)

    submit_video = _post(DOP_LITE_URL, {
        "prompt": video_prompt,
        "motions": [],
        "image_url": image_url,
        "enhance_prompt": True,
    })
    video_job = _wait_for_job(submit_video)
    video_url = _extract_url_from_job(video_job)

    urllib.request.urlretrieve(video_url, out_path)
    return out_path
