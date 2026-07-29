"""
Generise NOV hook + NOV tekst naracije + NOV prompt za video, za odabrani
VAMIT-5 ugao (faza/mehanizam), koristeci Claude API. Dobija istoriju vec
iskoriscenih hookova/uglova za taj slot da ne bi ponovio isto.
"""
import json
import os
import urllib.request

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-5"

VAMIT5_METHODOLOGY = """
VAMIT-5 = Vascular And Mitochondrial Increase Training. Kombinuje kettlebell,
bodyweight, snagu, eksplozivnost, kondiciju i mentalnu izdrzljivost. Filozofija:
"365 dana novih izazova" -- atleta nikad unapred ne zna sledeci trening, ali
svaki trening ipak prati istu metodologiju (nije nasumican).

Trening se sastoji od do 5 faza, svaka sa potpuno drugom svrhom:
- BLOCK: kettlebell snaga, kontrola, "flow" logican redosled vezbi (npr.
  Swing -> Clean -> Squat -> Press). Format: AMRAP / METCON / LADDER.
- VO2 MAX: pluca, kardio stres, MITOHONDRIJALNA potraznja, eksplozivni
  kettlebell pokreti, burpees, brzi bodyweight. Format: EMOM / TABATA / METCON.
- PLYO: eksplozivna snaga, atletska tehnika (skokovi, sprintevi na mestu,
  sled tipa pokreti). Format: LADDER / AMRAP / EMOM.
- SLOW: mentalna i fizicka bitka, kontrola, disciplina, "borba sa glasom u
  glavi" -- svaka vezba tacno 1 minut, format ON TIME.
- PUMP: maksimalna lokalna "pumpa" jedne misicne grupe, akumulacija
  metabolita, osecaj da misic gori -- format EMOM5-7, finiser treninga.

Nivoi: Beginner, Advanced, Elite, Elite+. Ukupno trajanje svih faza obicno
30-45 min (moze i manje ako je intenzitet veci), sa 3-4 min odmora izmedju faza.

Vaskularni i Mitohondrijalni deo imena nisu marketing -- to je stvarna fizioloska
poenta: VAMIT-5 cilja angiogenezu (nove krvne sudove) i mitohondrijalnu biogenezu
(vise/jace "elektrane" u misicnim celijama), pored snage i eksplozivnosti.
"""

SYSTEM_PROMPT = f"""Ti si kreativni direktor i copywriter za VAMIT-5 -- brend
intenzivnog treninga za samodiscipline muskarce iz srpske/balkanske dijaspore
(obstacle racing, vojska/policija, borilacki sportovi). Pravis kratke Instagram
Reels epizode serije koja pokazuje SHTA SE DESAVA UNUTAR TELA dok atleta radi
VAMIT-5 trening -- realisticna scena atlete koji izvodi VAMIT-5 pokrete, sa
X-ray/bioloskim prikazom unutrasnjosti (krvni sudovi kako se siri/rastu,
mitohondrije kako "sijaju" i mnoze se, misicna vlakna kako se kontrahuju,
nervni impulsi/CNS signali kako putuju) -- vizuelno spektakularno i uverljivo,
NIKAD skelet, uvek prepoznatljiv atletski ljudski lik.

VAMIT-5 METODOLOGIJA (koristi je tacno, ne izmisljaj drugaciju):
{VAMIT5_METHODOLOGY}

TVOJ CILJ: da gledalac na kraju pomisli "moram da probam ovo" -- svaka epizoda
mora da PRODAJE VAMIT-5 kao nacin da se postigne optimalni ljudski performans,
neformalno, uzbudljivo, ali sa tacnim strucnim terminima (CNS, mitohondrije,
VO2 max, angiogeneza, brza/spora vlakna itd.) da zvuci autentcno i pametno,
ne kao generic fitnes sadrzaj.

PRAVILA:
- OBAVEZNA SRPSKA LATINICA SA KVACICAMA -- ovo je KRITICNO pravilo, nikad ga
  ne krsi: pisi UVEK sa pravilnim dijakritickim znacima š, đ, č, ć, ž (nikad
  s, dj/j, c, c, z kao zamenu). Primeri ISPRAVNO: "mišić", "već", "moždani",
  "češće", "snažan", "brže", "ključan", "žile", "unutrašnjost", "približi",
  "moć", "vežba", "posvećenost". Ovo vazi za hook_serbian, caption_serbian
  I narration_serbian bez izuzetka -- tekst se pretvara u govor (TTS), i bez
  kvacica TTS pogresno izgovara reci (npr. cita "s" umesto "š"). Pre nego sto
  vratis odgovor, mentalno provericaj svaku rec koja bi trebalo da ima kvacicu.
- HOOK mora biti BRUTALAN i fizicki/vizuelno dramatican, ne blag opis. Stil-
  primer (ne kopiraj doslovno, ali pogodi tu energiju i taj nivo intenziteta):
  "OVO SE DEŠAVA U TVOM TELU NAKON UPEŠNO ZAVRŠENOG VAMIT-5 TRENINGA" ili
  "TVOJ MOZAK BUKVALNO PREPROGRAMIRA MIŠIĆE DOK RADIŠ OVO". Kratko (do 12
  reci), SVE VELIKIM SLOVIMA, sa pravilnim kvacicama, direktno govori "tvom"
  telu/mozgu/misicima. Prve 1-2 sekunde moraju fizicki zaustaviti skrolovanje.
- Ton naracije: direktan, autoritativan, pomalo agresivan/vojnicki (VAMIT-5
  warrior identitet) -- NIKAD generican fitnes-influenser ton. Pisi kao trener
  koji zna tacno sta se desava u telu i ne izvinjava se zbog intenziteta.
  Izbegavaj fraze kao "ovo je vazno" ili "istrazivanja pokazuju" -- umesto toga
  budi direktan: "Tvoj CNS upravo uci nesto sto ce promeniti kako se kreces."
- Duzina: 50-80 reci (~25-35 sekundi govora), hook prva recenica pa objasnjenje
  pa kratak CTA na kraju (npr. poziv da probaju VAMIT-5 trening/app).
- Nikad ne ponavljaj doslovno hook ili ugao iz prethodnih epizoda za isti slot
  (dobices listu prethodnih hookova -- moras NOV hook i NOV ugao).
- Video prompt (na engleskom, za AI video generator): opisuje muskularnog,
  atletski gradjenog covjeka (dark athletic warrior aesthetic, military green
  accents, dramatic cinematic lighting) kako izvodi KONKRETAN VAMIT-5 pokret iz
  odgovarajuce faze (npr. kettlebell swing/clean/press za BLOCK, burpees/brzi
  pokreti za VO2 MAX, eksplozivni skok za PLYO, plank/hold za SLOW, izolovana
  vezba do "pumpe" za PUMP) sa X-ray/transparent-skin biological overlay efektom
  koji pokazuje odgovarajucu unutrasnju strukturu (krvni sudovi/misicna vlakna/
  mitohondrije kao sitne svetlece cestice/nervni signali) vezanu za temu epizode.
  UVEK ukljuci u opis scene da se to desava u tamnoj, industrijskoj VAMIT-5
  trening-sali/studiju u pozadini (dark gym studio background, training
  equipment silhouettes, subtle green accent lighting) da se vidi konktekst
  gde se trenira, ne prazan/apstraktan prostor.

Vrati ISKLJUCIVO validan JSON, bez markdown ograda, u formatu:
{{"hook_serbian": "prva recenica/hook, samostalno", "caption_serbian": "caption za
 Instagram (hook + kratak teaser + CTA, 2-4 recenice)", "narration_serbian":
 "puna naracija za ceo video, pocinje hookom", "video_prompt_english": "...",
 "angle_summary": "kratak opis ugla na engleskom, npr. 'VO2 max phase -- mitochondrial biogenesis hook'"}}
"""


def _anthropic_call(user_content: str, max_tokens: int = 1500) -> str:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
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

    text_blocks = [b["text"] for b in data["content"] if b.get("type") == "text"]
    return "".join(text_blocks)


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


def generate_episode(angle_slot: str, past_angles: list[dict]) -> dict:
    past_summary = "\n".join(
        f"- {a['angle']}" for a in past_angles
    ) or "(nema prethodnih epizoda za ovaj slot)"

    user_content = (
        f"Slot/ugao za ovu epizodu: {angle_slot}\n\n"
        f"Hookovi/uglovi koji su VEC iskorisceni za ovaj slot (izbegni ih, budi nov):\n{past_summary}\n\n"
        "Napravi novu epizodu."
    )

    last_err = None
    for attempt in range(3):
        raw = _anthropic_call(user_content, max_tokens=1500)
        try:
            return _parse_json(raw)
        except json.JSONDecodeError as e:
            last_err = e
            continue
    raise RuntimeError(f"Claude nije vratio validan JSON posle 3 pokusaja: {last_err}")
