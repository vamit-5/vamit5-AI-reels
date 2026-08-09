"""
Pretvara tekst naracije u audio fajl koristeci ElevenLabs API
(Eleven v3 model -- najnoviji, najizrazajniji ElevenLabs model, podrzava
srpski i "audio tag" rezijske oznake tipa [excited]/[intense] koje menjaju
TON izgovora bez da menjaju sam izgovoreni tekst).

VOICE_ID mora biti dubok muski glas -- podesi u GitHub Secrets
(ELEVENLABS_VOICE_ID). Predlog: u ElevenLabs Voice Library pretrazi
"deep" + "male" + isprobaj sa srpskim tekstom pre nego sto odaberes,
zvuci se dosta razlikuju po jeziku iako je model isti.

Ako je skripta duga (audio bi trajao preko TARGET_MAX_SECONDS na
podrazumevanoj brzini), automatski se generise DRUGI put sa malo brzim
tempom da se ceo Reel skrati -- ali ogranicено na MAX_SPEED da ne pocne
da zvuci neprirodno/ubrzano-komicno.
"""
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
VOICE_ID = os.environ["ELEVENLABS_VOICE_ID"]

MAX_RETRIES = 5
LEAD_IN_MS = 350  # mala tisina na pocetku -- sprecava da se prva rec odsece

DEFAULT_SPEED = 1.1
MAX_SPEED = 1.2  # ElevenLabs realan gornji limit pre nego sto zvuk pocne neprirodno
TARGET_MAX_SECONDS = 60.0


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


# Audio tag(ovi) koji se dodaju SAMO u ono sto se salje ElevenLabs-u (rezijska
# uputstva, model ih NE izgovara) -- ne diraju tekst koji ide u caption/
# Instagram opis, jer se dodaju ovde, unutar TTS poziva, ne u sam narration_text.
# Rotiraju se KROZ CEO tekst (ne samo na pocetku) da energija ne opadne
# posle prvih par sekundi na duzim skriptama.
AUDIO_TAGS = ["[energetic]", "[enthusiastic]", "[upbeat]", "[lively]"]


def _inject_audio_tags(text: str) -> str:
    """Oznaka se stavlja SAMO na svaku 4. recenicu (ne na svaku!) -- previse
    oznaka zaredom teralo je model da pravi kratku pauzu/predah pre svake,
    sto je usporavalo govor i pravilo velike razmake izmedju recenica
    (i posledicno kvarilo sinhronizaciju captiona). Rec je izabrana da
    znaci "brzo/zivo", ne "dramaticno" (izbegava rec "intense"/"powerful"
    koje vise pozivaju na teatralnu pauzu)."""
    sentences = re.findall(r"[^.!?]+[.!?]?", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    tagged = []
    for i, s in enumerate(sentences):
        if i % 4 == 0:
            tag = AUDIO_TAGS[(i // 4) % len(AUDIO_TAGS)]
            tagged.append(f"{tag} {s}")
        else:
            tagged.append(s)
    return " ".join(tagged)


def _synthesize_at_speed(text: str, out_path: str, speed: float) -> str:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    tagged_text = _inject_audio_tags(text)
    payload = {
        "text": tagged_text,
        "model_id": "eleven_v3",
        "voice_settings": {
            "stability": 0.25,   # malo vise od pre (0.15) -- previse nisko je doprinosilo neizvesnim pauzama
            "similarity_boost": 0.8,
            "style": 0.85,       # jos malo vise energije/karaktera da nadoknadi manje ucestale oznake
            "use_speaker_boost": True,
            "speed": speed,
        },
    }
    body = json.dumps(payload).encode("utf-8")

    delay = 5
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "content-type": "application/json",
                "accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio_bytes = resp.read()
            raw_path = out_path + ".raw.mp3"
            with open(raw_path, "wb") as f:
                f.write(audio_bytes)
            # dodaj malu tisinu na pocetak da IG/telefon "zagrevanje" ne
            # pojede prvi deo prve reci
            subprocess.run(
                ["ffmpeg", "-y", "-i", raw_path,
                 "-af", f"adelay={LEAD_IN_MS}:all=1",
                 "-c:a", "libmp3lame", out_path],
                check=True, capture_output=True,
            )
            os.remove(raw_path)
            return out_path
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise RuntimeError(f"ElevenLabs trajna greska {e.code}: {e.read().decode(errors='ignore')}")
            last_err = e
        except urllib.error.URLError as e:
            last_err = e

        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"ElevenLabs TTS nije uspeo posle {MAX_RETRIES} pokusaja: {last_err}")


def synthesize(text: str, out_path: str) -> str:
    _synthesize_at_speed(text, out_path, DEFAULT_SPEED)
    duration = _probe_duration(out_path)

    if duration <= TARGET_MAX_SECONDS:
        return out_path

    # skripta je duza od cilja -- izracunaj koliko brzine treba da se
    # priblizimo TARGET_MAX_SECONDS, ali ne preko MAX_SPEED (da ostane
    # prirodno). Trajanje govora je priblizno obrnuto srazmerno brzini.
    needed_speed = DEFAULT_SPEED * (duration / TARGET_MAX_SECONDS)
    new_speed = min(MAX_SPEED, round(needed_speed, 2))

    if new_speed > DEFAULT_SPEED:
        print(f"Skripta duza od {TARGET_MAX_SECONDS:.0f}s ({duration:.1f}s na {DEFAULT_SPEED}x) "
              f"-- ponovo generisem na {new_speed}x")
        _synthesize_at_speed(text, out_path, new_speed)

    return out_path
