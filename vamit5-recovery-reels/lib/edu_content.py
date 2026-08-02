"""
Uzima FIKSNU skriptu (tekst se ne menja, dolazi iz lib/edu_scripts.py) i
pravi AI video prompt za svaki segment -- u DVA JEDNOSTAVNA KORAKA umesto
jednog komplikovanog (stari pristup je cesto pucao na velikom JSON
odgovoru, sto je vodilo ka genericnom rezervnom sadrzaju koji NIJE imao
veze sa tekstom -- to je bio pravi uzrok i ponavljanja i netacnog sadrzaja):

KORAK A: Claude deli numerisane recenice na N grupa -- SAMO brojevi
(pocetak/kraj), trivijalan JSON, skoro nemoguce da pukne.

KORAK B: za SVAKU grupu, poseban (jednostavan) poziv Claude-u koji vraca
CIST TEKST (ne JSON) -- video prompt za bas TU grupu recenica. Manji
zadatak = Claude mnogo preciznije "pogadja" sta se u toj grupi doslovno
prica, i skoro nikad ne pukne (nema JSON strukture da se pokvari).

Claude NE prepisuje/menja sam tekst naracije -- samo bira granice i pise
video promptove. Ovo garantuje da izgovoreni tekst ostaje 100% ono sto je
covek napisao.
"""
import json
import os
import random
import re
import urllib.request

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-5"

TARGET_CLIP_SECONDS = 6.5
MIN_SEGMENTS = 3
MAX_SEGMENTS = 12


def compute_segment_count(audio_dur: float) -> int:
    raw = round(audio_dur / TARGET_CLIP_SECONDS)
    return max(MIN_SEGMENTS, min(MAX_SEGMENTS, raw))


# ===== MEHANICKI FORSIRANA RAZLICITOST (ne oslanja se na Claude "trud") =====
# Za svaki segment se PRISILNO dodeljuje tacno odredjen ugao kamere i
# konkretan vizuelni detalj koji se GARANTOVANO dodaje na kraj prompta.
# Liste imaju vise stavki nego MAX_SEGMENTS, biraju se BEZ PONAVLJANJA
# unutar jednog videa.
CAMERA_ANGLES = [
    "extreme close-up shot on the face and upper shoulders",
    "wide shot showing the entire body from several meters away",
    "low camera angle looking upward for a dramatic powerful perspective",
    "side profile view from the left side",
    "over-the-shoulder view from behind the subject",
    "high top-down bird's eye view looking straight down",
    "medium shot framed from the waist up",
    "close angle focused on the hands and forearms",
    "wide establishing shot showing the whole environment first",
    "slightly low handheld-style angled shot",
    "extreme close-up on the eyes and forehead",
    "three-quarter angle view of the upper body",
    "close-up on the feet and legs during movement",
    "reverse angle shot facing toward the camera from the front",
]

VISUAL_DETAILS = [
    "wearing a plain black tank top",
    "wearing a dark olive green t-shirt",
    "with visible chalk dust on the hands",
    "with a sweat-soaked shirt",
    "wearing black training shorts",
    "with a black wristband on one wrist",
    "standing on a black rubber gym mat with visible texture",
    "next to a kettlebell with a red-painted handle",
    "with short messy dark hair",
    "with a plain grey concrete wall visible in the background",
    "wearing dark grey joggers",
    "with a water bottle visible on the floor nearby",
    "with a small hand towel draped over one shoulder",
    "with visible exposed brick wall in the background",
]

_FALLBACK_PROMPTS = [
    "Ordinary tired man walking up an apartment staircase carrying grocery bags, out of breath, leaning on the railing",
    "Confused man sitting on a couch scrolling through his phone, dozens of fitness app icons visible on screen, frustrated frown",
    "Athletic muscular man in a dark VAMIT-5 training studio performing a kettlebell swing, dynamic motion",
    "Athletic muscular man in a dark VAMIT-5 training studio holding a deep squat position, visible muscle tension",
    "Close-up biological X-ray overlay on an athlete's torso showing a glowing beating heart and blood vessels",
    "Group of determined people finishing a workout together in a dark VAMIT-5 studio, high fives, authentic emotion",
    "Middle-aged man looking at an old photo of himself, nostalgic expression, sitting on a couch",
    "Man standing in front of a mirror at home, contemplative expression, ordinary clothes",
    "Athletic man performing an explosive box jump in a dark gym studio",
    "Athletic man doing a plank hold, visible strain and focus on his face",
    "Man checking a smartwatch on his wrist, close-up on the screen showing heart rate",
    "Father playing with his child outdoors, energetic, genuine smiles",
]

PHOTOREAL_SUFFIX = (
    ", hyperrealistic, shot on DSLR camera, natural matte skin texture, "
    "NOT CGI, NOT 3D render, NOT shiny or oily skin, authentic candid "
    "fitness photography style, anatomically correct hands with five "
    "fingers, natural body proportions, no distorted limbs"
)


def _assign_forced_variety(segment_count: int):
    angles = random.sample(CAMERA_ANGLES, min(segment_count, len(CAMERA_ANGLES)))
    details = random.sample(VISUAL_DETAILS, min(segment_count, len(VISUAL_DETAILS)))
    while len(angles) < segment_count:
        angles += random.sample(CAMERA_ANGLES, min(segment_count - len(angles), len(CAMERA_ANGLES)))
    while len(details) < segment_count:
        details += random.sample(VISUAL_DETAILS, min(segment_count - len(details), len(VISUAL_DETAILS)))
    return angles[:segment_count], details[:segment_count]


def _anthropic_call(system_prompt: str, user_content: str, max_tokens: int) -> str:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(b["text"] for b in data["content"] if b.get("type") == "text")


# ===== KORAK A: SAMO granice (brojevi), trivijalan JSON =====

_SPLIT_SYSTEM = """Delis numerisanu skriptu na TACNO {segment_count} uzastopnih
grupa recenica, priblizno ravnomerno po broju reci (ne moraju biti bas
identicne duzine, ali izbegavaj da jedna grupa bude mnogo veca od ostalih).

Vrati ISKLJUCIVO validan JSON, bez ikakvog drugog teksta:
{{"boundaries": [[start0, end0], [start1, end1], ...]}}
gde su brojevi INDEKSI recenica (0-indeksirano, end je INKLUZIVNO),
tacno {segment_count} parova, bez rupa i bez preklapanja, pokrivaju SVE
recenice od prve do poslednje."""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


def _validate_boundaries(boundaries, num_sentences: int) -> bool:
    if not boundaries:
        return False
    expected_start = 0
    for pair in boundaries:
        if len(pair) != 2:
            return False
        s, e = pair
        if s != expected_start or e < s:
            return False
        expected_start = e + 1
    return expected_start == num_sentences


def _equal_boundaries(num_sentences: int, segment_count: int) -> list[list[int]]:
    n = min(segment_count, num_sentences) or 1
    base = num_sentences // n
    remainder = num_sentences % n
    boundaries, idx = [], 0
    for i in range(n):
        size = base + (1 if i < remainder else 0)
        if size == 0:
            continue
        boundaries.append([idx, idx + size - 1])
        idx += size
    return boundaries


def _split_boundaries(sentences: list[str], segment_count: int) -> list[list[int]]:
    numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(sentences))
    user_content = f"Skripta ({len(sentences)} recenica, numerisane):\n{numbered}"

    for attempt in range(4):
        try:
            raw = _anthropic_call(
                _SPLIT_SYSTEM.format(segment_count=segment_count),
                user_content, max_tokens=500,
            )
            data = _parse_json(raw)
            boundaries = data.get("boundaries", [])
            if _validate_boundaries(boundaries, len(sentences)):
                return boundaries
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue

    print("UPOZORENJE: podela na granice nije uspela, koristim ravnomernu podelu.")
    return _equal_boundaries(len(sentences), segment_count)


# ===== KORAK B: po JEDAN prompt, CIST TEKST (ne JSON -- skoro nemoguce da pukne) =====

_SCENE_SYSTEM = """Ti si vizuelni reziser za VAMIT-5 edukativne Instagram Reels.
Dobijas KRATAK isecak skripte i tvoj JEDINI posao je da opises JEDNU AI
generisanu scenu koja DOSLOVNO prikazuje o cemu se u tom isecku prica.

===== NAJVAZNIJE PRAVILO =====
Duboko razumi KONTEKST pre nego sto opises scenu -- ne default na "fit
tip u teretani" za sve:
- Svakodnevna muka obicnog coveka (npr. nosi kese, zadihan na stepenicama)
  -> obican, NE atletski gradjen covek, iscrpljen -- kontrast je poenta.
- Zbunjenost/neodlucnost (npr. previse aplikacija, ne zna sta da radi)
  -> covek zbunjeno gleda u telefon, frustriran izraz lica.
- Tekst DOSLOVNO opisuje VAMIT-5 trening/pokret (cucanj, kettlebell,
  eksplozivan pokret) -> TEK TADA atletski gradjen covek u VAMIT-5
  studiju kako TACNO izvodi TAJ pokret.
- Unutrasnja fiziologija (srce, mozak/CNS, misicna vlakna, mitohondrije)
  -> X-ray/transparent-skin bioloski overlay koji pokazuje TACNO taj organ.
- Ako tekst pominje "Balkan", "Balkanci", ili konkretnu balkansku zemlju
  -> OBAVEZNO ukljuci prepoznatljiv balkanski element u scenu (npr.
  zastava Srbije/Hrvatske/BiH/Crne Gore vidljiva u pozadini, balkanski
  pejzaz/planine, ili slican prepoznatljiv simbol) -- ne izostavljaj ovo.
- Emocija/nostalgija/porodica -> konkretna ljudska scena koja to
  ilustruje, ne apstraktan opis.

STIL (uvek primeni): hiperrealisticno, kao DSLR fotografija, prirodna
matirana koza (NE sjajna/plasticna/CGI), anatomski tacno telo (5 prstiju
po saci, prirodne proporcije, bez izoblicenja), realisticno osvetljenje,
vertikalan 9:16 kadar.

Odgovori ISKLJUCIVO cistim tekstom video prompta na ENGLESKOM (1-3
recenice), BEZ navodnika, BEZ markdown, BEZ ikakvog dodatnog objasnjenja
ili uvoda -- samo sam opis scene, spreman da se posalje AI generatoru."""


def _generate_scene_prompt(segment_text: str, camera: str, detail: str) -> str:
    user_content = (
        f"Isecak skripte za ovu scenu: \"{segment_text}\"\n\n"
        f"Scena MORA koristiti ovaj kadar: {camera}\n"
        f"Scena MORA ukljuciti ovaj detalj: {detail}"
    )
    try:
        raw = _anthropic_call(_SCENE_SYSTEM, user_content, max_tokens=300)
        prompt = raw.strip().strip('"')
        if prompt:
            return f"{prompt}{PHOTOREAL_SUFFIX}"
    except Exception as e:
        print(f"UPOZORENJE: generisanje scene za segment nije uspelo ({e}), koristim rezervnu scenu.")

    return None  # signal caller-u da koristi fallback


def split_into_segments(sentences: list[str], segment_count: int) -> list[dict]:
    boundaries = _split_boundaries(sentences, segment_count)
    forced_angles, forced_details = _assign_forced_variety(len(boundaries))

    segments = []
    for i, (start, end) in enumerate(boundaries):
        segment_text = " ".join(sentences[start:end + 1])
        camera = forced_angles[i]
        detail = forced_details[i]

        prompt = _generate_scene_prompt(segment_text, camera, detail)
        if prompt is None:
            # rezervna scena -- i dalje razlicita po indeksu, i dalje sa
            # prisilno dodeljenim kadrom/detaljem, samo generic sadrzaj
            base = _FALLBACK_PROMPTS[i % len(_FALLBACK_PROMPTS)]
            prompt = f"{base}. Camera angle: {camera}. Visual detail: {detail}.{PHOTOREAL_SUFFIX}"

        segments.append({"start": start, "end": end, "video_prompt_english": prompt})

    return segments
