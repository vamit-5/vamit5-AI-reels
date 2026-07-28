"""
Upload finalnog mp4 na Cloudinary preko unsigned upload preset-a
(identican pristup kao postojeca automatizacija).
"""
import json
import os
import time
import urllib.request
import urllib.error

CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
UPLOAD_PRESET = os.environ["CLOUDINARY_UPLOAD_PRESET"]

MAX_RETRIES = 5


def upload_video(path: str) -> str:
    url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/video/upload"

    with open(path, "rb") as f:
        video_bytes = f.read()

    boundary = "----vamit5boundary"
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"upload_preset\"\r\n\r\n{UPLOAD_PRESET}\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"episode.mp4\"\r\nContent-Type: video/mp4\r\n\r\n")
    header = "".join(parts).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + video_bytes + footer

    delay = 5
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["secure_url"]
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise RuntimeError(f"Cloudinary trajna greska {e.code}: {e.read().decode(errors='ignore')}")
            last_err = e
        except urllib.error.URLError as e:
            last_err = e

        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"Cloudinary upload nije uspeo posle {MAX_RETRIES} pokusaja: {last_err}")
