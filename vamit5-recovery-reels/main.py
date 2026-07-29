"""
Glavni ulazni fajl. Pokrece ga GitHub Actions (cron + workflow_dispatch).

Tok:
1. Pokusaj da zauzmes lock -- ako neko drugi vec radi, tiho izadji
2. Odaberi sledecu vremensku tacku (rotacija) i istoriju uglova za nju
3. Claude API generise nov tekst naracije + video prompt (nikad ponovljen ugao)
4. ElevenLabs generise audio
5. Higgsfield generise video po promptu
6. ffmpeg spaja video+audio+caption+watermark u finalni Reels
7. Cloudinary hostuje finalni fajl
8. Instagram Graph API objavljuje Reels
9. Upisuje se novo stanje (state.json) i lock se otkljucava, sve se commit-uje
"""
import datetime
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import state as state_lib
from lib import theme, tts, video, assemble, cloudinary_upload, instagram, lock

HASHTAGS = "#vamit5 #kettlebell #trening #optimalniperformans #srbija #disciplina #mentalnasnaga #fitness"


def _in_allowed_window() -> bool:
    """
    cron-job.org zove workflow svakih ~15-18 min kao 'budilnik', ali stvarna
    objava treba da se desi samo u odredjenim satima (UTC). Format env
    promenljive ALLOWED_UTC_HOUR_WINDOWS: "17-19,20-21" (pocetak-kraj, moze
    vise opsega odvojenih zarezom). Ako promenljiva nije podesena, uvek
    dozvoljava (korisno za rucni workflow_dispatch test).
    """
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
    if not _in_allowed_window():
        print("Van dozvoljenog vremenskog prozora -- tiho izlazim (bez objave).")
        return

    acquired = lock.try_acquire()
    if not acquired:
        print("Lock zauzet od strane drugog pokretanja -- tiho izlazim.")
        return

    try:
        st = state_lib.load_state()
        time_point, idx = state_lib.pick_next_time_point(st)
        past_angles = st.get("history", {}).get(str(idx), [])

        print(f"Generisem epizodu za: {time_point}")
        episode = theme.generate_episode(time_point, past_angles)

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "narration.mp3")
            tts.synthesize(episode["narration_serbian"], audio_path)

            raw_video_path = os.path.join(tmp, "raw.mp4")
            video.generate_episode_video(
                episode["video_prompt_english"], episode["video_prompt_english"], raw_video_path
            )

            final_path = os.path.join(tmp, "final.mp4")
            assemble.assemble(
                raw_video_path, audio_path,
                caption_text=episode["narration_serbian"],
                time_point_label=episode["hook_serbian"],
                out_path=final_path,
                tmp_dir=tmp,
            )

            public_url = cloudinary_upload.upload_video(final_path)

            full_caption = f"{episode['caption_serbian']}\n\n{HASHTAGS}"
            post_id = instagram.publish_reel(public_url, full_caption)
            print(f"Objavljeno na Instagram, post id: {post_id}")

        st = state_lib.record_episode(st, idx, episode["angle_summary"], episode["caption_serbian"])
        state_lib.save_state(st)

        lock.release_and_commit(
            [state_lib.STATE_PATH],
            f"chore: objavljena epizoda '{time_point}' (post {post_id})",
        )

    except Exception:
        traceback.print_exc()
        lock.release_and_commit([], "chore: release lock posle greske")
        sys.exit(1)


if __name__ == "__main__":
    main()
