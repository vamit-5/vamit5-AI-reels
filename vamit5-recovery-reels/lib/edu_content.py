"""
Uzima FIKSNU skriptu (tekst se ne menja, dolazi iz lib/edu_scripts.py) i
preko Claude API-ja je deli na N segmenata (grupe recenica), gde za svaki
segment Claude smislja odgovarajuci AI video prompt KOJI DOSLOVNO PRIKAZUJE
sta se u tom delu teksta desava/opisuje.

Bitno: Claude NE prepisuje/menja sam tekst naracije -- samo bira granice
(indekse recenica) i pise video prompt. Ovo garantuje da izgovoreni tekst
ostaje 100% ono sto je covek napisao.
"""
import json
import os
import random
import urllib.request

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-5"

# ===== MEHANICKI FORSIRANA RAZLICITOST (ne oslanja se na Claude "trud") =====
# Za svaki segment se PRISILNO dodeljuje tacno odredjen ugao kamere i
# konkretan vizuelni detalj koji Claude MORA da ukljuci u prompt. Ovo je
# garantovana strukturna razlika, nezavisna od toga koliko su segmenti
# sadrzajno slicni. Liste imaju vise stavki nego MAX_SEGMENTS, i biraju se
# BEZ PONAVLJANJA unutar jednog videa (random.sample).
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


def _assign_forced_variety(segment_count: int):
    """Nasumicno bira RAZLICIT ugao kamere i RAZLICIT vizuelni detalj za
    svaki od segment_count segmenata -- bez ponavljanja unutar ovog videa."""
    angles = random.sample(CAMERA_ANGLES, min(segment_count, len(CAMERA_ANGLES)))
    details = random.sample(VISUAL_DETAILS, min(segment_count, len(VISUAL_DETAILS)))
    # ako je segment_count > duzina liste (retko, MAX_SEGMENTS=12 blizu duzine
    # listi), popuni ciklicno da ne pukne
    while len(angles) < segment_count:
        angles += random.sample(CAMERA_ANGLES, min(segment_count - len(angles), len(CAMERA_ANGLES)))
    while len(details) < segment_count:
        details += random.sample(VISUAL_DETAILS, min(segment_count - len(details), len(VISUAL_DETAILS)))
    return angles[:segment_count], details[:segment_count]

# Broj segmenata NIJE fiksan -- racuna se dinamicki na osnovu trajanja
# audija, tako da svaki segment otprilike odgovara prirodnoj duzini JEDNOG
# AI klipa (5-8 sekundi). Ovo sprecava da se isti klip PETLJA unutar
# predugackog segmenta (sto bi izgledalo kao ponavljanje iste scene).
TARGET_CLIP_SECONDS = 6.5
MIN_SEGMENTS = 3
MAX_SEGMENTS = 12  # gornja granica zbog Higgsfield troska


def compute_segment_count(audio_dur: float) -> int:
    raw = round(audio_dur / TARGET_CLIP_SECONDS)
    return max(MIN_SEGMENTS, min(MAX_SEGMENTS, raw))

SYSTEM_PROMPT = """Ti si vizuelni reziser za VAMIT-5 edukativne Instagram Reels
epizode. Dobijas skriptu (vec podeljenu na numerisane recenice) i tvoj posao
je da:

1. Podelis te recenice u TACNO {segment_count} uzastopnih grupa (segmenata) --
   svaka recenica mora pripadati tacno jednom segmentu, bez preskakanja i bez
   preklapanja, pokrivajuci SVE recenice od prve do poslednje.
2. Za svaki segment napises video_prompt_english -- opis AI generisane scene.

===== NAJVAZNIJE PRAVILO (procitaj dva puta) =====
Scena MORA doslovno prikazivati sta se U TOM DELU TEKSTA dogadja/opisuje --
ne generican "fit trener u teretani" default za sve. Duboko razumi KONTEKST
recenice pre nego sto opises scenu:

- Ako tekst opisuje SVAKODNEVNU muku obicnog coveka (npr. "izadjes iz
  prodavnice sa dve kese, popnes se na treci sprat i staneš ispred vrata kao
  da čekas medicinski tim") -> prikazi OBICNOG, NE-atletski gradjenog,
  zadihanog coveka kako nosi kese, oslanja se na zid, iscrpljen -- NE
  mišićavog sportistu. Kontrast je poenta.
- Ako tekst opisuje ZBUNJENOST/neodlucnost (npr. "ne mora svaki dan da
  smišljas šta da radiš") -> prikazi coveka kako zbunjeno gleda u telefon
  na kom se vidi desetine fitnes aplikacija, ne zna sta da izabere,
  frustriran izraz lica -- NE osobu u teretani.
- Ako tekst DOSLOVNO opisuje VAMIT-5 trening/vezbu/pokret (npr. cucanj,
  kettlebell, eksplozivan pokret) -> TEK TADA prikazi atletski gradjenog
  coveka u VAMIT-5 studiju kako TACNO IZVODI taj pokret.
- Ako tekst govori o UNUTRASNJOJ fiziologiji (srce, mozak/CNS, misicna
  vlakna, mitohondrije) -> prikazi X-ray/transparent-skin bioloski overlay
  koji pokazuje TACNO taj organ/sistem (srce kako kuca, nervni signali,
  mitohondrije kao svetlece cestice, itd.)
- Ako tekst govori o ZAJEDNICI/motivaciji/emociji -> prikazi konkretnu
  ljudsku scenu koja to ilustruje (grupa ljudi, izraz lica pun odlucnosti,
  itd.), NE apstraktan opis.

===== STROGO ZABRANJENO (APSOLUTNO, BEZ IZUZETKA) =====
- NIKAD ne koristi isti/skoro isti opis scene za dva razlicita segmenta,
  CAK NI KAD dva ili vise uzastopnih segmenata pricaju o istoj opstoj temi
  (npr. oba pominju "VAMIT-5 trening" ili oba pominju "snagu"). Opsta tema
  NIJE izgovor za istu scenu -- svaki segment MORA da se razlikuje u SVE
  TRI stvari istovremeno:
    1) KO je u kadru (razlicit tip coveka/ljudi, razlicita gradja, razlicita
       odeca/kontekst)
    2) KOJA konkretna radnja se desava (razlicit pokret, razlicita poza,
       razlicita akcija -- ne "trenira" uopsteno, nego TACNO koji pokret)
    3) KAKAV je kadar/ugao kamere (krupni plan lica, siroki plan celog tela,
       pogled odozgo, iz profila, itd. -- variraj)
  Ako od {segment_count} promptova bilo koja DVA licE slicno kad ih
  zamislis kao slike, POGRESIO SI -- vrati se i promeni.
- NIKAD ne padaj na default "mišićavi tip u teretani" ako tekst opisuje
  nesto drugo (svakodnevni zivot, emociju, zbunjenost, umor obicnog coveka).
  Taj default je DOZVOLJEN iskljucivo kad tekst DOSLOVNO opisuje VAMIT-5
  trening pokret, i cak i tada svaki takav segment mora imati RAZLICIT
  konkretan pokret i razlicit kadar od svakog drugog treninga-segmenta.
- Pre nego sto vratis odgovor, mentalno prodji kroz sve {segment_count}
  promptove jedan po jedan i proveri da nijedna dva ne opisuju vizuelno
  slicnu scenu. Ovo pravilo je vaznije od bilo kog drugog u ovom uputstvu.

STIL (primeni na SVAKU scenu, bez obzira na sadrzaj) -- ovo je JEDNAKO
VAZNO kao i sadrzaj scene, procitaj pazljivo:
HIPERREALISTICNO, neprepoznatljivo od stvarne fotografije snimljene
profesionalnim DSLR fotoaparatom ili modernim telefonom -- NE 3D render, NE
CGI, NE "video game" izgled, NE preterano poliran/uljan/plastican izgled
koze. Koza mora izgledati kao PRAVA LJUDSKA KOZA -- matirana, sa prirodnom
teksturom, porama, sitnim nesavrsenostima, NE sjajna/masna/plasticna.

ANATOMSKA TACNOST JE OBAVEZNA -- ovo je cest AI problem, budi eksplicitan:
tacno 5 prstiju na svakoj saci, prirodne proporcije tela, prirodni oblik
lica bez izoblicenja, ruke i noge u anatomski moguc polozaj, bez visak/
manjak udova ili prstiju, lice simetricno i realno. Uvek dodaj u prompt:
"anatomically correct hands with five fingers, natural body proportions,
no distorted limbs, no extra or missing fingers, photorealistic human
face and body, indistinguishable from a real photograph".

Prirodno, realisticno osvetljenje (moze biti tamna prostorija sa suptilnim
zelenim akcentnim svetlom, ali izvor svetla i senke moraju delovati fizicki
verovatno, ne kao render). Zamisli da opisujes kadar iz autenticne fitnes
fotografije ili amaterskog telefonskog snimka -- NE filmski poster, NE
video-igra, NE hiper-stilizovana CGI scena. Vertikalan 9:16 kadar.

Vrati ISKLJUCIVO validan JSON (bez markdown ograda), u formatu:
{{"segments": [{{"start": 0, "end": 2, "video_prompt_english": "..."}}, ...]}}
gde su "start" i "end" INDEKSI recenica (0-indeksirano, end je INKLUZIVNO),
tacno {segment_count} segmenata, bez rupa i bez preklapanja.

KRITICNO ZA FORMAT: unutar video_prompt_english NIKAD ne koristi dvostruke
navodnike (") -- to kvari JSON. Koristi apostrofe (') ako moras da istakneš
nešto.
"""


def _anthropic_call(user_content: str, segment_count: int) -> str:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 3000,
        "system": SYSTEM_PROMPT.format(segment_count=segment_count),
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


# Rezervne scene (SAMO ako Claude nikako ne uspe da vrati validan JSON posle
# svih pokusaja) -- namerno RAZLICITE jedna od druge da se izbegne
# ponavljanje istog klipa, ali ovo je krajnja mera, ne normalan put
_PHOTOREAL_SUFFIX = (
    ", hyperrealistic, shot on DSLR camera, natural matte skin texture, "
    "NOT CGI, NOT 3D render, NOT shiny or oily skin, authentic candid "
    "fitness photography style, anatomically correct hands with five "
    "fingers, natural body proportions, no distorted limbs"
)

_FALLBACK_PROMPTS = [
    "Ordinary tired man walking up an apartment staircase carrying grocery "
    "bags, out of breath, leaning on the railing" + _PHOTOREAL_SUFFIX,
    "Confused man sitting on a couch scrolling through his phone, dozens of "
    "fitness app icons visible on screen, frustrated frown" + _PHOTOREAL_SUFFIX,
    "Athletic muscular man in a dark VAMIT-5 training studio performing a "
    "kettlebell swing, dynamic motion, subtle green accent light" + _PHOTOREAL_SUFFIX,
    "Athletic muscular man in a dark VAMIT-5 training studio holding a deep "
    "squat position, visible muscle tension, subtle green accent light" + _PHOTOREAL_SUFFIX,
    "Close-up biological X-ray overlay on an athlete's torso showing a "
    "glowing beating heart and blood vessels, dark background, subtle green "
    "accent light" + _PHOTOREAL_SUFFIX,
    "Group of determined people finishing a workout together in a dark "
    "VAMIT-5 studio, high fives, authentic emotion" + _PHOTOREAL_SUFFIX,
]


def _fallback_equal_split(num_sentences: int, segment_count: int) -> list[dict]:
    """Ako Claude ne vrati validnu podelu, napravi prostu ravnomernu podelu
    umesto da ceo workflow pukne -- ali sa RAZLICITIM promptovima po
    segmentu, ne istim ponovljenim, da se klipovi ne dupliraju vizuelno."""
    print("UPOZORENJE: Claude segmentacija nije uspela, koristim rezervnu podelu.")
    n = min(segment_count, num_sentences) or 1
    base = num_sentences // n
    remainder = num_sentences % n
    segments, idx = [], 0
    for i in range(n):
        size = base + (1 if i < remainder else 0)
        if size == 0:
            continue
        segments.append({
            "start": idx,
            "end": idx + size - 1,
            "video_prompt_english": _FALLBACK_PROMPTS[i % len(_FALLBACK_PROMPTS)],
        })
        idx += size
    return segments


def _validate_segments(segments: list[dict], num_sentences: int) -> bool:
    if not segments:
        return False
    covered = sorted((s["start"], s["end"]) for s in segments)
    expected_start = 0
    for start, end in covered:
        if start != expected_start or end < start:
            return False
        expected_start = end + 1
    return expected_start == num_sentences


def split_into_segments(sentences: list[str], segment_count: int) -> list[dict]:
    forced_angles, forced_details = _assign_forced_variety(segment_count)

    numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(sentences))
    assignments = "\n".join(
        f"- Segment {i}: MORA koristiti kadar '{forced_angles[i]}' I MORA "
        f"ukljuciti detalj '{forced_details[i]}'"
        for i in range(segment_count)
    )
    user_content = (
        f"Skripta (recenice numerisane):\n{numbered}\n\n"
        "Podeli je i napravi video promptove. Duboko razmisli o KONTEKSTU "
        "svake grupe recenica pre nego sto opises scenu -- ne default na "
        "'fit tip u teretani' ako tekst opisuje nesto drugo.\n\n"
        f"OBAVEZNA DODELA PO SEGMENTU (ukljuci doslovno u odgovarajuci "
        f"video_prompt_english):\n{assignments}"
    )

    segments = None
    last_err = None
    for attempt in range(5):
        try:
            raw = _anthropic_call(user_content, segment_count)
            data = _parse_json(raw)
            candidate = data.get("segments", [])
            if _validate_segments(candidate, len(sentences)):
                segments = candidate
                break
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            last_err = e
            continue

    if segments is None:
        print(f"UPOZORENJE: segmentacija nije validna posle 5 pokusaja: {last_err}")
        segments = _fallback_equal_split(len(sentences), segment_count)

    # GARANCIJA (ne zavisi od toga da li je Claude poslusan): prisilno
    # dodaj dodeljeni ugao i detalj na kraj SVAKOG prompta, cak i ako ga
    # Claude vec pomenuo -- ponavljanje istog detalja u tekstu ne steti,
    # ali izostavljanje bi ponistilo celu garanciju razlicitosti
    for i, seg in enumerate(segments):
        angle = forced_angles[i] if i < len(forced_angles) else forced_angles[i % len(forced_angles)]
        detail = forced_details[i] if i < len(forced_details) else forced_details[i % len(forced_details)]
        seg["video_prompt_english"] = (
            f"{seg['video_prompt_english']}. Camera angle: {angle}. "
            f"Visual detail: {detail}."
        )

    return segments
