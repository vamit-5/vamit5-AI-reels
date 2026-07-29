"""
Glavni ulazni fajl. Pokrece ga GitHub Actions (cron + workflow_dispatch).

Tok:
1. Pokusaj da zauzmes lock -- ako neko drugi vec radi, tiho izadji
2. Odaberi sledecu gotovu skriptu (rotacija u krug)
3. ElevenLabs generise audio (tacan tekst, bez izmena)
4. Sa Google Drive-a preuzmi sledeci video snimak i sledecu muziku
   (rotacija, nikad isti fajl dva puta zaredom)
5. ffmpeg spaja: video (loop) + glas + muzika (ducked) + hook caption +
   logo + CTA mockup na kraju
6. Cloudinary hostuje finalni fajl
7. Instagram Graph API objavljuje Reels
8. Upisuje se novo stanje i lock se otkljucava, sve se commit-uje
"""
import datetime
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import state as state_lib
from lib import theme, tts, gdrive, assemble, cloudinary_upload, instagram, lock

HASHTAGS = "#vamit5 #kettlebell #trening #srbija #disciplina #mentalnasnaga #fitness"


def _in_allowed_window() -> bool:
    windows = os.environ.get("ALLOWED_UTC_HOUR_WINDOWS", "").strip()
    if not windows:
        return True
    current_hour = datetime.datetime.utcnow().hour
    for part in windows.split(","):
        start, end = part.split("-")
        if int(start) <= current_hour < int(end):
            return True
    return False


def main():
    # rucno pokretanje (dugme "Run workflow") uvek prolazi odmah, bez obzira
    # na sat -- ogranicenje vazi SAMO za automatski (cron/budilnik) raspored
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if not is_manual and not _in_allowed_window():
        print("Van dozvoljenog vremenskog prozora -- tiho izlazim (bez objave).")
        return

    acquired = lock.try_acquire()
    if not acquired:
        print("Lock zauzet od strane drugog pokretanja -- tiho izlazim.")
        return

    try:
        st = state_lib.load_state()

        episode = theme.select_episode(st)
        print(f"Skripta #{episode['script_index']}: {episode['hook_serbian'][:60]}...")

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "narration.mp3")
            tts.synthesize(episode["narration_serbian"], audio_path)

            videos, audios = gdrive.list_files()
            video_item = gdrive.pick_next(videos, st.get("last_video_id"))
            raw_video_path = os.path.join(tmp, "raw_video.mp4")
            gdrive.download_file(video_item["id"], raw_video_path)
            print(f"Video: {video_item['name']}")

            music_item = None
            if audios:
                music_item = gdrive.pick_next(audios, st.get("last_audio_id"))
                music_raw_path = os.path.join(tmp, "music_raw.mp3")
                gdrive.download_file(music_item["id"], music_raw_path)
                print(f"Muzika: {music_item['name']}")

            final_path = os.path.join(tmp, "final.mp4")
            assemble.assemble(
                raw_video_path, audio_path,
                narration_text=episode["narration_serbian"],
                out_path=final_path,
                tmp_dir=tmp,
            )

            public_url = cloudinary_upload.upload_video(final_path)

            full_caption = f"{episode['caption_serbian']}\n\n{HASHTAGS}"
            post_id = instagram.publish_reel(public_url, full_caption)
            print(f"Objavljeno na Instagram, post id: {post_id}")

        st["next_script_index"] = episode["script_index"] + 1  # theme.py radi % len(SCRIPTS) pri citanju
        st["last_video_id"] = video_item["id"]
        if music_item:
            st["last_audio_id"] = music_item["id"]
        state_lib.save_state(st)

        lock.release_and_commit(
            [state_lib.STATE_PATH],
            f"chore: objavljena skripta #{episode['script_index']} (post {post_id})",
        )

    except Exception:
        traceback.print_exc()
        lock.release_and_commit([], "chore: release lock posle greske")
        sys.exit(1)


if __name__ == "__main__":
    main()
