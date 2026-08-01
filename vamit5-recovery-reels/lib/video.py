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
import random
import time
import urllib.request
import urllib.error

HIGGSFIELD_API_KEY = os.environ["HIGGSFIELD_API_KEY"].strip()
HIGGSFIELD_API_SECRET = os.environ["HIGGSFIELD_API_SECRET"].strip()

SOUL_URL = "https://platform.higgsfield.ai/v1/text2image/soul"
DOP_LITE_URL = "https://platform.higgsfield.ai/higgsfield-ai/dop/lite"
STATUS_URL_TMPL = "https://platform.higgsfield.ai/requests/{request_id}/status"

POLL_INTERVAL_SECONDS = 8
MAX_POLL_MINUTES = 18
MAX_SUBMIT_RETRIES = 2  # ako istekne vreme, probaj ponovo od nule (nov seed)


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

    # Higgsfield koristi razlicita imena polja na razlicitim endpoint-ima
    # (Soul vraca "id", DoP Lite vraca "request_id") -- zato prvo probamo
    # da uzmemo "status_url" direktno (uvek prisutan, najpouzdaniji nacin),
    # a tek ako ga nema, sastavljamo URL rucno iz id/request_id polja
    status_url = submit_response.get("status_url")
    if not status_url:
        request_id = submit_response.get("id") or submit_response.get("request_id")
        if not request_id:
            raise RuntimeError(f"Nema request_id/status_url u Higgsfield odgovoru: {submit_response}")
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
        # queued / in_progress -> nastavi da ceka
    raise TimeoutError("Higgsfield generisanje je isteklo (timeout)")


def _extract_url_from_job(job):
    # Higgsfield koristi razlicita imena polja zavisno od endpointa/faze:
    # "video" (jednina, dict) je poseban slucaj -- proveri prvo njega
    video_field = job.get("video")
    if isinstance(video_field, dict) and isinstance(video_field.get("url"), str):
        return video_field["url"]

    # "results", "images", "videos" (mnozina, liste), ili direktno "url"
    for list_key in ("results", "images", "videos"):
        items = job.get(list_key)
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                for key in ("url", "image_url", "video_url"):
                    if isinstance(first.get(key), str):
                        return first[key]
        if isinstance(items, dict):
            for key in ("url", "image_url", "video_url"):
                if isinstance(items.get(key), str):
                    return items[key]
    for key in ("url", "output_url", "video_url", "image_url"):
        if isinstance(job.get(key), str):
            return job[key]
    raise RuntimeError(f"Nisam nasao URL rezultata u zavrsenom poslu: {job}")


def _download(url, out_path):
    # urlretrieve ne salje nase custom header-e (User-Agent) pa CDN server
    # (isto kao Cloudflare ranije) vraca 403 -- zato preuzimamo rucno
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp, open(out_path, "wb") as f:
        f.write(resp.read())


def _generate_image(image_prompt: str, rng) -> str:
    for attempt in range(MAX_SUBMIT_RETRIES + 1):
        submit_image = _post(SOUL_URL, {
            "params": {
                "prompt": image_prompt,
                "quality": "1080p",
                "batch_size": 1,
                "enhance_prompt": False,  # ne dozvoljavamo Higgsfield-u da sam dodaje "cinematic" stilizaciju
                "style_strength": 1,
                "width_and_height": "1536x1536",
                "seed": rng.randint(1, 1_000_000),
            }
        })
        try:
            image_job = _wait_for_job(submit_image)
            return _extract_url_from_job(image_job)
        except TimeoutError:
            print(f"UPOZORENJE: generisanje slike isteklo, pokusaj {attempt + 1}/{MAX_SUBMIT_RETRIES + 1}")
            continue
    raise RuntimeError("Higgsfield generisanje slike nije uspelo posle vise pokusaja (timeout)")


def _generate_video_from_image(video_prompt: str, image_url: str, rng) -> str:
    for attempt in range(MAX_SUBMIT_RETRIES + 1):
        submit_video = _post(DOP_LITE_URL, {
            "prompt": video_prompt,
            "motions": [],
            "image_url": image_url,
            "enhance_prompt": False,  # ne dozvoljavamo Higgsfield-u da sam dodaje "cinematic" stilizaciju
            "seed": rng.randint(1, 1_000_000),
        })
        try:
            video_job = _wait_for_job(submit_video)
            return _extract_url_from_job(video_job)
        except TimeoutError:
            print(f"UPOZORENJE: generisanje videa isteklo, pokusaj {attempt + 1}/{MAX_SUBMIT_RETRIES + 1}")
            continue
    raise RuntimeError("Higgsfield generisanje videa nije uspelo posle vise pokusaja (timeout)")


def generate_episode_video(image_prompt: str, video_prompt: str, out_path: str) -> str:
    # KRITICNO: eksplicitno saljemo NASUMICAN seed na SVAKI poziv (i za
    # sliku i za video, odvojeno) -- bez ovoga Higgsfield ume da koristi
    # neki podrazumevani/slican seed sto pravi vizuelno skoro-identicne
    # klipove uprkos razlicitim promptovima. random.SystemRandom koristi
    # OS izvor entropije (ne obican pseudo-random), maksimalna nasumicnost.
    rng = random.SystemRandom()

    image_url = _generate_image(image_prompt, rng)
    video_url = _generate_video_from_image(video_prompt, image_url, rng)

    _download(video_url, out_path)
    return out_path
