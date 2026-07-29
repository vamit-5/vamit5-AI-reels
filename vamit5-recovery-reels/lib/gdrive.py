"""
Cita fajlove iz Google Drive foldera (video snimci + mp3 muzika, isti folder)
preko Service Account-a, rotira ih redom (bez ponavljanja istog fajla dva
puta zaredom) i preuzima izabrani fajl lokalno.

Potrebne biblioteke: google-api-python-client, google-auth
"""
import io
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

FOLDER_ID = os.environ["GDRIVE_FOLDER_ID"]
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _get_service():
    raw_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def list_files():
    """Vraca sve fajlove iz foldera, podeljene na video i audio liste (imena fajlova)."""
    service = _get_service()
    videos, audios = [], []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token,
        ).execute()
        for f in resp.get("files", []):
            mime = f.get("mimeType", "")
            entry = {"id": f["id"], "name": f["name"]}
            if mime.startswith("video/") or f["name"].lower().endswith(".mp4"):
                videos.append(entry)
            elif mime.startswith("audio/") or f["name"].lower().endswith(".mp3"):
                audios.append(entry)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    # sortiraj po imenu da redosled bude predvidljiv/stabilan izmedju pokretanja
    videos.sort(key=lambda x: x["name"])
    audios.sort(key=lambda x: x["name"])
    return videos, audios


def download_file(file_id: str, out_path: str):
    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(out_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return out_path


def pick_next(items: list, last_id: str | None):
    """
    Rotira redom kroz listu (po abecedi imena, stabilno izmedju pokretanja).
    Nikad ne vraca isti fajl koji je bio poslednji put izabran (osim ako
    lista ima samo 1 fajl).
    """
    if not items:
        raise RuntimeError("Nema fajlova u Drive folderu za ovu kategoriju (video/audio).")

    ids = [i["id"] for i in items]
    if last_id in ids:
        idx = (ids.index(last_id) + 1) % len(items)
    else:
        idx = 0
    return items[idx]
