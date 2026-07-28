# VAMIT-5 -- "Sta se desava u telu" Reels (automatska generacija + objava)

Serija Reels-ova koja pokazuje atletu kako izvodi VAMIT-5 pokrete uz X-ray/bioloski
prikaz unutrasnjosti tela (krvni sudovi, mitohondrije, misicna vlakna, CNS), sa jakim
hookom na pocetku i ciljem da ubedi gledaoca da proba VAMIT-5.

Svaki put kad se pokrene, sistem:
1. Bira sledeci "slot" -- jednu VAMIT-5 fazu ili fizioloski mehanizam (BLOCK, VO2 MAX,
   PLYO, SLOW, PUMP, vaskularni/mitohondrijalni efekat, hormoni, 365-dana filozofija,
   regeneracija, "VAMIT-5 vs teretana", prvi trening pocetnika...), rotira u krug
2. Claude API (sa ugradjenom VAMIT-5 metodologijom) pise NOV hook + naraciju + caption +
   video prompt -- nikad ne ponavlja isti hook/ugao za isti slot
3. ElevenLabs pretvara tekst u govor (dubok glas, srpski)
4. Higgsfield generise video: atleta izvodi konkretan VAMIT-5 pokret (kettlebell swing,
   burpees, eksplozivni skok, plank hold...) sa X-ray bioloskim overlay efektom
5. ffmpeg spaja video + audio + hook (gornja traka) + caption + VAMIT-5 vodeni zig
6. Cloudinary hostuje fajl privremeno
7. Instagram Graph API objavljuje kao Reels, sa caption-om koji ima CTA

## Pre prvog pokretanja -- sta treba da napravis

### 1. Novi Instagram nalog
Ako jos nije napravljen, napravi poseban Instagram Business/Creator nalog za ovaj sadrzaj i
povezi ga sa Meta Business Suite (isto kao za glavni VAMIT-5 nalog).

### 2. Anthropic API kljuc (Claude)
console.anthropic.com -> API Keys -> Create Key. Ovo koristimo za pisanje teksta/uglova.

### 3. ElevenLabs
- Napravi nalog na elevenlabs.io (besplatan plan: 10.000 karaktera mesecno, dovoljno za
  desetak epizoda -- ako ti zatreba vise, prelazi se na placeni plan kasnije)
- Profile -> API Keys -> kopiraj kljuc
- Voice Library -> pretrazi "deep male" glasove i PUSTI PROBNI SNIMAK NA SRPSKOM teksta pre
  nego sto odaberes (glasovi zvuce razlicito po jeziku iako je model isti) -- kopiraj Voice ID
  odabranog glasa

### 4. Higgsfield (vec imas nalog)
- platform.higgsfield.ai -> API Keys -> napravices API Key + API Secret (dva odvojena dela)
- higgsfield.ai/create/video -> isprobaj rucno par modela sa promptom u stilu "muscular
  athlete performing kettlebell swing, dark military green cinematic lighting, X-ray
  biological overlay showing glowing blood vessels and muscle fibers" i vidi koji model_id
  (vidi se u dokumentaciji/playground meniju) daje najbolji "atleta + X-ray overlay" izgled
  bez da atleta izgleda izobliceno -- to je HIGGSFIELD_MODEL_ID. Vredi isprobati i modele
  koji podrzavaju "consistent character" (Soul mode) da isti atleta izgleda isto iz epizode
  u epizodu -- prepoznatljivost je bitna za brend.

### 5. Cloudinary (ako vec nemas iz prethodne automatizacije, mozes iskoristiti isti nalog)
- Settings -> Upload -> Add upload preset -> Signing Mode: Unsigned -> zapamti ime preseta

### 6. Instagram/Meta pristup
- Isti postupak kao za postojecu automatizaciju: Meta Developer app -> Instagram API use case
  -> generisi dugotrajan Access Token i pribavi Instagram Business Account ID novog naloga

## GitHub podesavanje

1. Napravi nov privatan GitHub repo, otpakuj ove fajlove u njega
2. Settings -> Actions -> General -> Workflow permissions -> "Read and write permissions" -> Save
3. Settings -> Secrets and variables -> Actions -> New repository secret, dodaj SVAKI od ovih
   (nalepis vrednost, meni koje NIKAD ne saljes u chat):
   - `ANTHROPIC_API_KEY`
   - `ELEVENLABS_API_KEY`
   - `ELEVENLABS_VOICE_ID`
   - `HIGGSFIELD_API_KEY`
   - `HIGGSFIELD_API_SECRET`
   - `HIGGSFIELD_MODEL_ID`
   - `CLOUDINARY_CLOUD_NAME`
   - `CLOUDINARY_UPLOAD_PRESET`
   - `IG_ACCESS_TOKEN`
   - `IG_BUSINESS_ACCOUNT_ID`
4. Ubaci VAMIT-5 logo (providan PNG, kvadratan) kao `assets/vamit5_logo.png` u repo (watermark
   u donjem desnom uglu videa) -- ako ga preskocis, kod radi i bez njega, samo bez vodenog ziga
5. Actions tab -> izaberi "VAMIT-5 Hyrox Recovery Reels" -> "Run workflow" za rucni test
6. Ako test uspe, podesi spoljasnji "budilnik" na cron-job.org (isti kao za postojecu
   automatizaciju) da zove workflow_dispatch svakih ~15-18 min -- `main.py` sam prepoznaje
   dozvoljeni prozor (`ALLOWED_UTC_HOUR_WINDOWS` u workflow fajlu, sad podeseno na 17-19h UTC
   = ~19-21h po srpskom vremenu) i tiho preskace van njega

## Napomene

- Besplatan ElevenLabs plan (10.000 karaktera/mesec) je ogranicenje -- ako ti ponestane
  karaktera pre kraja meseca, TTS poziv ce vratiti gresku i workflow ce se zaustaviti (ne
  objavljuje polovicnu epizodu). Prati potrosnju na elevenlabs.io/app/usage.
- Higgsfield generisanje kosta kredite po pozivu (zavisno od modela/rezolucije) -- proveri
  cenu izabranog modela pre nego sto postavis dnevni raspored.
- Prva 1-2 nedelje preporucujem RUCNO pokretanje (workflow_dispatch) i pregled par objava pre
  nego sto ukljucis pun automatski raspored -- da vidis da li ti se svidja stil videa/glasa.
