"""
Definicije za "volumen" tok (46 reels-a dnevno iz 3 Drive foldera).

Svaki folder ima svoje pravilo za zvuk/tekst:
- MUTE_MUSIC_TEXT ("Ugasi ton"): ugasi original zvuk, dodaj muziku, dodaj tekst
- KEEP_TEXT ("Ostavi ton"): zadrzi original zvuk, dodaj tekst, BEZ muzike
- MUTE_MUSIC_NOTEXT ("Ne dodavaj tekst + dodaj muziku"): ugasi original zvuk,
  dodaj muziku, BEZ teksta

Tekstovi na snimcima (8 komada) rotiraju se u krug, NEZAVISNO od rotacije
video snimaka (dva odvojena brojaca u state.json).
"""
import os

MODE_MUTE_MUSIC_TEXT = "mute_music_text"
MODE_KEEP_TEXT = "keep_text"
MODE_MUTE_MUSIC_NOTEXT = "mute_music_notext"

# folder_id se cita iz GitHub Secrets (setuj: GDRIVE_FOLDER_MUTE_TEXT,
# GDRIVE_FOLDER_KEEP_TEXT, GDRIVE_FOLDER_MUTE_NOTEXT)
# needs_voice: da li se dodaje ElevenLabs naracija (iz lib/scripts.py pool-a)
# REDOSLED U OVOJ LISTI = REDOSLED ROTACIJE (folder1 -> folder2 -> folder3 ->
# ponovo folder1...). needs_voice: da li se dodaje ElevenLabs naracija
# (iz lib/scripts.py pool-a)
FOLDERS = [
    {"key": "mute_text", "folder_id": os.environ.get("GDRIVE_FOLDER_MUTE_TEXT", ""), "mode": MODE_MUTE_MUSIC_TEXT, "needs_voice": True},
    {"key": "keep_text", "folder_id": os.environ.get("GDRIVE_FOLDER_KEEP_TEXT", ""), "mode": MODE_KEEP_TEXT, "needs_voice": False},
    {"key": "mute_notext", "folder_id": os.environ.get("GDRIVE_FOLDER_MUTE_NOTEXT", ""), "mode": MODE_MUTE_MUSIC_NOTEXT, "needs_voice": True},
]

CAPTION_TEXTS = [
    'Komentariši "VAMIT" i dobijaš 7 dana besplatan VAMIT-5 App',
    "Balkanci, ulazite u VAMIT-5 (7 dana besplatno)",
    "Sagori do 800 kalorija za 40 minuta (link u BIO)",
    "Treba ti balkanska motivacija za trening? Zahvali se posle!",
    "Nema ko da te motiviše za trening? Uđi u VAMIT-5!",
    "Za one kojima treba balkanska motivacija u treningu!",
    "Za Balkance koji znaju ko su",
    "Za one kojima treba balkanska zajednica!",
]

FIXED_CTA_BLOCK = (
    "\n\n@vamit5_ @vamit5.athletes\n"
    "Testiraj VAMIT-5 App 7 dana besplatno. Link u BIO.\n"
    "#joinvamit5"
)
