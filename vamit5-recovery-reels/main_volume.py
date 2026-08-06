"""
Glavni fajl za "volumen" tok -- 46 reels-a dnevno iz 3 Drive foldera
(razliciti tretman zvuka/teksta po folderu), BEZ ElevenLabs glasa.

Pokrece ga GitHub Actions cesto (na par minuta) tokom celog aktivnog
prozora (07:00-00:00 po srpskom vremenu) -- ALI stvarno objavljuje samo
kada je proteklo dovoljno vremena od poslednje objave (samo-regulisuci
razmak, jer GitHub-ov cron nije precizan na minut). Cilj: ~24 objave u
prozoru 07-17h (svakih ~25 min) i ~24 objave u prozoru 17-00h (svakih
~17.5 min).
"""
import datetime
import os
import random
import sys
import shutil
import subprocess
import time
import tempfile
import traceback
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import state as state_lib
from lib import gdrive, volume_content, volume_assemble, cloudinary_upload, instagram, lock, tts
from lib import assemble as full_assemble
from lib.scripts import SCRIPTS


def _caption_from_script(text: str, max_chars: int = 220) -> str:
    """Uzima pocetak skripte za Instagram opis, ali SAMO cele recenice
    (nikad ne sece nasred recenice/reci)."""
    sentences = full_assemble._split_sentences(text)
    result = ""
    for s in sentences:
        candidate = f"{result} {s}".strip() if result else s
        if len(candidate) > max_chars and result:
            break
        result = candidate
    return result or text[:max_chars]

BELGRADE_TZ = ZoneInfo("Europe/Belgrade")

WINDOW_A_START, WINDOW_A_END = 7, 17    # 07:00-17:00 -> 24 objave, ~25 min razmak
WINDOW_B_START, WINDOW_B_END = 17, 24   # 17:00-00:00 -> 24 objave, ~17.5 min razmak
INTERVAL_A_MIN = 600 / 24  # 25.0
INTERVAL_B_MIN = 420 / 24  # 17.5

HASHTAGS = "#vamit5 #kettlebell #trening #disciplina #fitness"


def _required_interval_minutes(local_now: datetime.datetime) -> float | None:
    hour = local_now.hour
    if WINDOW_A_START <= hour < WINDOW_A_END:
        return INTERVAL_A_MIN
    if WINDOW_B_START <= hour < WINDOW_B_END:
        return INTERVAL_B_MIN
    return None  # van aktivnog prozora


def _is_true_manual_click() -> bool:
    """Pravi rucni klik na 'Run workflow' (bez inputa/podrazumevano 'manual').
    GitHub-ov ugradjeni cron I spoljasnji cron-job.org budilnik (koji salje
    source='cron') se NE racunaju kao rucni -- oni MORAJU postovati razmak."""
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    trigger_source = os.environ.get("TRIGGER_SOURCE", "manual")
    return event_name == "workflow_dispatch" and trigger_source == "manual"


def _should_post_now(state: dict) -> bool:
    if _is_true_manual_click():
        print("Rucno pokretanje -- zaobilazim proveru razmaka izmedju objava.")
        return True

    now_local = datetime.datetime.now(BELGRADE_TZ)
    interval = _required_interval_minutes(now_local)
    if interval is None:
        print(f"Van aktivnog prozora (lokalno vreme {now_local.strftime('%H:%M')}) -- tiho izlazim.")
        return False

    last_at = state.get("last_volume_post_at")
    if not last_at:
        return True

    last_dt = datetime.datetime.fromisoformat(last_at)
    elapsed_min = (datetime.datetime.now(datetime.timezone.utc) - last_dt).total_seconds() / 60
    if elapsed_min < interval:
        print(f"Prosleklo samo {elapsed_min:.1f} min (treba {interval:.1f} min) -- tiho izlazim.")
        return False
    return True


def _pick_next_folder_and_video(state: dict):
    """
    Strogo rotira REDOM kroz foldere (folder1 -> folder2 -> folder3 ->
    ponovo folder1...), a UNUTAR izabranog foldera bira sledeci video po
    NJEGOVOJ sopstvenoj rotaciji (odvojeno pracenje po folderu, da se
    ravnomerno prodje kroz sve klipove u svakom folderu).
    """
    available_folders = [f for f in volume_content.FOLDERS if f["folder_id"]]
    if not available_folders:
        raise RuntimeError("Nijedan od 3 volumen foldera nije podesen (folder_id prazan).")

    folder_idx = state.get("next_volume_folder_index", 0) % len(available_folders)
    folder = available_folders[folder_idx]

    videos, _ = gdrive.list_files(folder["folder_id"])
    if not videos:
        raise RuntimeError(f"Nema video snimaka u folderu '{folder['key']}'.")

    last_by_folder = state.get("last_volume_video_id_by_folder", {})
    last_id = last_by_folder.get(folder["key"])
    video = gdrive.pick_next(videos, last_id)

    video_item = {**video, "mode": folder["mode"], "folder_key": folder["key"]}
    return video_item, folder_idx, len(available_folders)


def main():
    is_manual = _is_true_manual_click()

    # LOCK VAZI UVEK (i za rucna pokretanja) -- ovo je jedina prava zastita
    # od dva pokretanja koja se preklapaju i biraju isti snimak. Ako je
    # zauzet, sacekaj kratko i probaj ponovo par puta (rucno pokretanje
    # ne treba dugo da ceka, ali NE SME da preskoci lock potpuno)
    acquired = False
    for attempt in range(6):
        acquired = lock.try_acquire()
        if acquired:
            break
        if is_manual:
            print(f"Lock zauzet, cekam 10s i probam ponovo ({attempt + 1}/6)...")
            time.sleep(10)
        else:
            break
    if not acquired:
        print("Lock zauzet od strane drugog pokretanja -- tiho izlazim.")
        return

    try:
        st = state_lib.load_state()

        if not _should_post_now(st):
            lock.release_and_commit([], "chore: volume - nije vreme za objavu, oslobadjam lock")
            return

        video_item, folder_idx, folder_count = _pick_next_folder_and_video(st)
        print(f"Video: {video_item['name']} (folder: {video_item['folder_key']}, mode: {video_item['mode']})")

        # KRITICNO: pomeri i SACUVAJ rotaciju foldera ODMAH, pre same obrade
        # -- ako ovaj video/folder posle ovoga padne (npr. Cloudinary
        # limit), sledeci pokusaj ide na SLEDECI folder, ne zaglavljuje se
        # beskonacno na istom problematicnom folderu. Lock OSTAJE zauzet
        # (koristimo commit_only, ne release_and_commit).
        st["next_volume_folder_index"] = (folder_idx + 1) % folder_count
        state_lib.save_state(st)
        lock.commit_only(
            [state_lib.STATE_PATH],
            f"chore: volume - rotacija pomerena na sledeci folder ({video_item['folder_key']} izabran)",
        )

        with tempfile.TemporaryDirectory() as tmp:
            raw_video_path = os.path.join(tmp, "raw_video.mp4")
            gdrive.download_file(video_item["id"], raw_video_path)

            needs_music = video_item["mode"] == volume_content.MODE_MUTE_MUSIC_TEXT
            music_raw_path = None
            music_item = None
            if needs_music:
                _, audios = gdrive.list_files()  # glavni (originalni) folder -- muzika
                if audios:
                    music_item = gdrive.pick_next(audios, st.get("last_volume_audio_id"))
                    # MORA da se zove bas "music_raw.mp3" -- assemble.finalize() ga
                    # trazi pod tim tacnim imenom da bi automatski umesao muziku
                    music_raw_path = os.path.join(tmp, "music_raw.mp3")
                    gdrive.download_file(music_item["id"], music_raw_path)
                    print(f"Muzika: {music_item['name']}")

            needs_voice = next(
                (f["needs_voice"] for f in volume_content.FOLDERS if f["key"] == video_item["folder_key"]),
                False,
            )
            script_idx = st.get("next_volume_script_index", 0)
            caption_idx = st.get("next_volume_caption_index", 0)
            final_path = os.path.join(tmp, "final.mp4")

            if needs_voice:
                # Folder "Ugasi ton": original zvuk se gasi, ElevenLabs cita
                # skriptu, video se petlja da traje tacno koliko traje govor,
                # caption PRATI govor (kao kod AI reels-ova), muzika 15-20%
                # u pozadini.
                script_text = SCRIPTS[script_idx % len(SCRIPTS)]
                voice_path = os.path.join(tmp, "voice.mp3")
                tts.synthesize(script_text, voice_path)
                print(f"Skripta #{script_idx % len(SCRIPTS)} (glas + sync caption)")

                full_assemble.assemble(
                    raw_video_path, voice_path,
                    narration_text=script_text,
                    out_path=final_path,
                    tmp_dir=tmp,
                )
                ig_caption_text = _caption_from_script(script_text)

            elif video_item["mode"] == volume_content.MODE_KEEP_TEXT:
                # Folder "Ostavi ton": original zvuk ostaje, dodaje se
                # kratak staticni natpis (rotira u krug), BEZ muzike/glasa
                caption_text = volume_content.CAPTION_TEXTS[caption_idx % len(volume_content.CAPTION_TEXTS)]
                print(f"Natpis: {caption_text}")
                volume_assemble.assemble_volume(
                    raw_video_path, video_item["mode"], None,
                    caption_text, final_path, tmp,
                )
                ig_caption_text = caption_text

            else:
                # Folder "Postavi bez izmena" (ranije "Ne dodavaj tekst..."):
                # POTPUNO NETAKNUTO -- original video i original zvuk,
                # bez ikakve obrade (bez teksta, muzike, loga, mockup-a)
                print("Postavljam original snimak -- laka kompresija (isti sadrzaj/kadar/zvuk, samo manji fajl da stane na Cloudinary).")
                subprocess.run(
                    ["ffmpeg", "-y", "-i", raw_video_path,
                     "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                     "-c:a", "aac", "-b:a", "192k",
                     final_path],
                    check=True, capture_output=True,
                )
                ig_caption_text = ""

            public_url = cloudinary_upload.upload_video(final_path)

            separator = "\n\n" if ig_caption_text else ""
            full_caption = f"{ig_caption_text}{separator}{volume_content.FIXED_CTA_BLOCK}\n\n{HASHTAGS}"
            post_id = instagram.publish_reel(public_url, full_caption)
            print(f"Objavljeno na Instagram, post id: {post_id}")

        st.setdefault("last_volume_video_id_by_folder", {})[video_item["folder_key"]] = video_item["id"]
        if music_item:
            st["last_volume_audio_id"] = music_item["id"]
        if needs_voice:
            st["next_volume_script_index"] = script_idx + 1
        if video_item["mode"] == volume_content.MODE_KEEP_TEXT:
            st["next_volume_caption_index"] = caption_idx + 1
        st["last_volume_post_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        state_lib.save_state(st)

        lock.release_and_commit(
            [state_lib.STATE_PATH],
            f"chore: volume objava ({video_item['folder_key']}, post {post_id})",
        )

    except Exception:
        traceback.print_exc()
        lock.release_and_commit([], "chore: release lock posle greske (volume)")
        sys.exit(1)


if __name__ == "__main__":
    main()
