# Time Capsule

Aplicație Django pentru păstrarea scrisorilor și amintirilor într-o capsulă digitală, sigilată până la o dată aleasă.

Repository: https://github.com/dianuca/time-capsule

## Scop și sursa stadiului

Acest document este planul de produs și checklist-ul de implementare pentru Codex în VS Code. Stadiul curent a fost verificat în cod și prin teste la 13 octombrie 2026; secțiunile istorice păstrează rezultatele etapelor anterioare. Codex trebuie să verifice codul, branch-ul și testele înainte de lucru și să actualizeze checklist-ul după verificare. Nu reimplementa funcționalități care există deja.

Versiunile sunt cumulative. Prioritatea este finalizarea V1; V2-V4 sunt extensii ulterioare.

## Stack și structură

- Python și Django 6.1.2; versiunile exacte instalate sunt în `requirements.txt`.
- Django Templates, CSS și JavaScript; păstrează structura existentă.
- SQLite în dezvoltare; PostgreSQL planificat pentru producție.
- Django Auth cu modelul `accounts.User`, bazat pe `AbstractUser`.
- Django Admin pentru administrare.
- Teste Django și Makefile.
- `config/`: setări și rute principale.
- `accounts/`: autentificare și preferințe.
- `capsules/`: modele, formulare, views și teste pentru capsule.
- `templates/`: template-uri comune și pagini.
- `static/css/style.css`: stilurile existente.

Nu introduce SPA, API REST, biblioteci UI sau servicii noi fără o nevoie concretă. Refolosește componentele existente.

## Pornire locală

Din rădăcina repository-ului, creează și activează mediul virtual dacă nu există.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Dacă activarea este blocată de politica PowerShell, permite scripturile doar pentru terminalul curent:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Instalare și verificare

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Pentru Admin, creează local un utilizator cu `python manage.py createsuperuser`.

Dacă Make este disponibil, cu mediul virtual activ:

```bash
make run
make check
make test
make migrations
make migrate
```

Nu publica `.env`, `.venv`, `db.sqlite3`, fișiere încărcate sau credențiale. Verifică configurația reală a variabilelor de mediu înainte de pornire; nu înlocui secretele cu valori publice pentru a elimina o eroare.

## Stadiu confirmat

- [x] Setup Django, repository și branch-uri pentru funcționalități.
- [x] Model propriu User, cu `timezone` și `email_notifications_enabled`.
- [x] Model Capsule cu UUID, owner, title, description, message și opens_at.
- [x] Câmpuri sealed_at și first_opened_at; proprietăți is_draft și is_available.
- [x] Înregistrare, login și logout prin POST.
- [x] Homepage responsive.
- [x] Lista privată „Capsulele mele”, filtrată după proprietar.
- [x] Crearea unei capsule ca ciornă.
- [x] Validarea datei viitoare și interpretarea orei în fusul utilizatorului la creare/editare.
- [x] Editarea ciornelor proprii; acces 404 pentru alt proprietar, 403 pentru capsulă sigilată.
- [x] Makefile și teste pentru homepage, autentificare, listare, creare și editare.

Ultima verificare locală, la 13 octombrie 2026: 95 de teste trec, inclusiv 19 teste pentru fotografii și 10 teste pentru integrarea lor în formular. `make check`, testele dedicate și `make test`, cu `PYTHON=.venv/Scripts/python.exe`, trec. `makemigrations --check --dry-run` nu detectează schimbări neacoperite de migrări. Numerele din secțiunile istorice de mai jos descriu verificările de la implementarea fiecărei etape.

Crearea, listarea privată, editarea ciornelor, filtrele după stare, căutarea, temele, sigilarea, deschiderea și fotografiile private sunt implementate. Reflecțiile și setările/notificările V1 rămân neimplementate. Editarea și sigilarea folosesc scrieri condiționate atomice; upload-ul și eliminarea fotografiilor serializează scrierile prin rândul capsulei. Admin afișează câmpurile capsulelor sigilate doar pentru lectură și respinge salvările întârziate.

## Reguli de produs și acces

1. Capsulele sunt private implicit.
2. Proprietarul vine din `request.user`, niciodată din POST.
3. Ciornele pot fi modificate. Sigilarea fixează conținutul și data deschiderii.
4. Proprietarul poate șterge o capsulă indiferent de stare, după confirmare.
5. GET afișează pagini; POST execută creare, editare, ștergere, sigilare și prima deschidere. Păstrează CSRF.
6. Scopează toate căutările de obiecte după owner sau apartenență. UUID-ul nu este o măsură de autorizare.
7. Nu trimite mesajele sau fișierele unei capsule blocate către browser, nici în HTML ascuns, JSON sau atribute data.
8. Deblocarea rezultă din ora serverului și `opens_at`; nu depinde de cron sau de livrarea emailului.
9. Stochează momente timezone-aware în UTC și afișează-le în fusul utilizatorului. Gestionează orele ambigue/inexistente la schimbarea orei.
10. Staff nu primește automat acces în paginile utilizatorilor. Revizuiește separat permisiunile și editarea în Admin.
11. Sigilarea, editarea și upload-urile trebuie să respecte aceeași regulă de blocare inclusiv la cereri simultane.
12. Blocarea este o regulă a aplicației, nu o promisiune că administratorii infrastructurii nu pot accesa datele.

## V1 - MVP personal

### 1. Ștergerea capsulelor - implementată

Branch sugerat: `feature/capsule-delete`.

- [x] View și rută scoped după proprietar.
- [x] GET afișează confirmarea fără să șteargă și fără să expună mesajul unei capsule blocate.
- [x] POST șterge, afișează un mesaj de succes și redirecționează la listă.
- [x] Link „Șterge” pe card, disponibil și pentru capsule sigilate/deschise.
- [x] Acțiune „Anulează” în confirmare.
- [x] Teste: anonim respins, alt proprietar 404 pe GET/POST, GET nu șterge, POST șterge doar obiectul vizat.
- [x] Când există atașamente, șterge și fișierele din storage după commit, cu reîncercare persistentă pentru erori.

Testele verifică suplimentar CSRF, accesul staff la capsule străine, metodele HTTP nepermise, ștergerea în toate stările și cererile repetate.

Verificarea vizuală în browser nu a fost disponibilă. Manual, pe desktop și mobil: deschide „Capsulele mele”, verifică linkul „Șterge” pe carduri, confirmarea, revenirea prin „Anulează” și mesajul de succes după ștergere.

### 2. Sigilare și integritatea conținutului - implementată

Branch sugerat: `feature/capsule-seal`.

- [x] Confirmare cu data și fusul orar; explică faptul că mesajul și data nu mai pot fi modificate.
- [x] Sigilare numai prin POST, doar pentru proprietar și doar cu dată viitoare.
- [x] Cere un mesaj nevid înainte de sigilare; fotografiile sunt opționale în V1.
- [x] Salvează sealed_at pe server; o cerere repetată nu resetează momentul.
- [x] Centralizează regulile într-un service reutilizat de views și Admin unde este cazul.
- [x] Protejează atomic sigilarea și scrierile concurente prin UPDATE condiționat, compatibil cu SQLite și PostgreSQL; nu depinde de select_for_update.
- [x] Revizuiește editarea existentă și Admin pentru a preveni modificarea conținutului/datei după sigilare.
- [x] Teste pentru autorizare, dată expirată, mesaj gol, repetare și blocarea editării după sigilare, inclusiv simularea unei sigilări în timpul validării formularului și respingerea salvării unui snapshot vechi.

### 3. Pagina capsulei și deschiderea

Branch sugerat: `feature/capsule-open`.

- [x] Pagină proprie pentru capsulă: titlu, descriere, stare și data locală; afișare în modal din colecție.
- [x] Pentru capsula blocată: numărătoare inversă în JS, cu fallback lizibil fără JS.
- [x] Înainte de termen, conținutul nu este inclus în răspuns și accesul direct la deschidere este refuzat (403 la POST; GET afișează doar metadatele).
- [x] La termen apare acțiunea „Deschide capsula”; modalul revalidează disponibilitatea pe server când numărătoarea ajunge la zero.
- [x] POST înregistrează first_opened_at o singură dată prin UPDATE condiționat atomic; apoi lectura este disponibilă prin GET.
- [x] Ciornele se citesc/editează fără a marca prima deschidere.
- [x] Animație scurtă de desfășurare a scrisorii, cu respectarea prefers-reduced-motion.
- [x] Teste înainte/la/după termen, acces străin, prima deschidere repetată și lipsa conținutului în răspunsurile blocate.

Validare: 8 teste noi pentru deschidere; suita totală are 55 de teste. Răspunsurile detaliilor folosesc `Cache-Control: no-store`; mesajul este escap-at la afișare. Verificarea animației și a modalului în browser rămâne manuală: deschide o capsulă demo disponibilă, confirmă, închide și recitește; verifică și o capsulă blocată, numărătoarea inversă și preferința de mișcare redusă.

### 4. Fotografii private - implementate

Stabilizarea galeriei: fotografia curentă rămâne vizibilă până când următoarea este încărcată și decodată; imaginile vecine sunt preîncărcate. Navigarea rapidă ignoră încărcările întârziate. Înălțimea cadrului și spațiul pentru numele fișierului sunt fixe, iar modalul rezervă spațiul scrollbar-ului pentru a evita salturile laterale. Cele 8 teste JavaScript includ încărcarea lentă, navigarea rapidă și erorile de decodare; cele 95 de teste Django trec. Verificarea vizuală în browser rămâne manuală.

La lectura capsulei, fotografiile sunt afișate într-o galerie cu o imagine principală, săgeți circulare anterior/următor, indicatorul `1/N` și numele imaginii. Sunt disponibile săgețile tastaturii, Home/End și swipe orizontal pe mobil; pentru o singură imagine se afișează `1/1` fără săgeți. Galeria se inițializează și când capsula este deschisă în modal. Fără JavaScript sunt afișate toate imaginile. Accesul privat înainte de prima deschidere rămâne blocat. Testele de navigare JavaScript se rulează cu `node --test static/js/tests/capsule-gallery.test.cjs` (8 scenarii, DOM simulat); aspectul și gesturile în browser necesită verificare manuală.

Branch sugerat: `feature/capsule-photos`.

- [x] Model Attachment și upload în ciornă; JPEG, PNG și WebP.
- [x] Limite: 10 imagini/capsulă, 5 MB/imagine; validează formatul real și dimensiunile imaginii (25 megapixeli, maximum 12000 px pe latură).
- [x] Permite eliminarea imaginilor înainte de sigilare, numai prin POST cu CSRF.
- [x] Stocare privată; acces prin endpoint autorizat, fără URL public și cu `Cache-Control: no-store`.
- [x] Galerie după prima deschidere și previzualizare în ciornă.
- [x] Upload/delete respectă sigilarea inclusiv în concurență, prin UPDATE condiționat al capsulei în tranzacția atașamentelor; limita totală este verificată după obținerea blocării pentru scriere.
- [x] Teste pentru fișiere invalide, limite, acces străin, acces înainte de termen și curățarea fișierelor, inclusiv rollback, erori storage și sigilare în timpul validării upload-ului.

Instalare: `python -m pip install -r requirements.txt`, apoi `python manage.py migrate`. Pillow 12.3.0 este folosit pentru decodare, verificare și resalvarea pixelilor; metadatele EXIF/GPS și datele adăugate după imagine sunt eliminate. Imaginile animate sunt respinse. Formatul este determinat din conținut, nu din extensie sau MIME-ul trimis de browser. Fișierul `requirements.txt` este acum UTF-8 pentru editare reproductibilă.

Fotografiile sunt integrate în formularul de creare/editare, sub scrisoare; nu există buton separat în colecție. „Adaugă” permite selectarea mai multor imagini, cu miniaturi locale și renunțare înainte de salvare. Selectările succesive se cumulează. Bifează o imagine existentă pentru eliminare; o poți debifa înainte de salvare. Mesajul, tema, data, imaginile noi și eliminările se salvează în aceeași tranzacție. Anularea formularului nu modifică imaginile existente. Limita de 10 se aplică totalului rămas, deci poți înlocui imagini când capsula este deja la limită.

În modal, fișierele selectate sunt păstrate după erorile de validare în browserele care permit reconstruirea selecției prin `DataTransfer`. Previzualizările folosesc URL-uri blob temporare, eliberate la închidere sau schimbarea selecției. Fără JavaScript funcționează formularul multipart și bifele de eliminare; după o eroare la submit trebuie reselectate fișierele noi.

După sigilare, endpoint-ul imaginilor refuză accesul până la prima deschidere, chiar dacă termenul a trecut. HTML-ul capsulelor blocate nu include imaginile sau URL-urile lor.

Storage local: `PRIVATE_MEDIA_ROOT` din `config/settings.py` indică `private_media/`, exclus din Git. Nu configura servirea publică a acestui director în Django sau în proxy. Pentru producție trebuie configurat un volum privat persistent și inclus în backup, împreună cu DB; setează în proxy limite de upload potrivite pentru maximum 10 fișiere de 5 MB. Configurarea producției rămâne în etapa 8.

La ștergerea unei imagini, capsule sau a unui cont, se creează în aceeași tranzacție un job `PendingFileDeletion`; fișierul este eliminat numai după commit. Erorile sunt înregistrate și păstrate pentru reîncercare: `python manage.py cleanup_private_files`. Comanda poate fi rulată periodic și după un incident storage; la oprirea procesului înainte de callback, jobul rămâne în DB. Upload-urile parțial eșuate anulează înregistrările și programează curățarea fișierelor deja scrise. Un rollback al ștergerii păstrează fișierele.

Validare locală pe SQLite: 95 de teste trec, inclusiv 10 teste noi pentru creare cu fotografii, înlocuire la limită, eliminări străine refuzate, validare, conflicte cu sigilarea și rollback comun pentru mesaj/fișiere. PostgreSQL și verificarea vizuală în browser nu au fost disponibile. Manual pe desktop/mobil: creează o capsulă cu JPEG/PNG/WebP, verifică miniaturile, apoi editează mesajul și înlocuiește o imagine la aceeași salvare. Verifică renunțarea la o imagine nouă, anularea eliminării uneia existente, anularea formularului, limita de 10, un fișier invalid și păstrarea selecției după o eroare de validare. Sigilează și verifică blocarea imaginilor; la termen deschide capsula și verifică galeria.

### 5. Reflecția după deschidere - următoarea prioritate

- [ ] Model Reflection: o reflecție personală per capsulă în V1.
- [ ] Creare/editare numai după prima deschidere, de către proprietar.
- [ ] Întrebări orientative: ce s-a schimbat, ce s-a împlinit, ce te-a surprins?
- [ ] Acțiune explicită pentru o nouă ciornă pornind din reflecție; fără copiere automată a datelor la GET.
- [ ] Teste pentru permisiuni și blocarea înainte de deschidere.

### 6. Colecție și teme

- [x] Filtre: toate, ciorne, sigilate, disponibile, deschise; stări mutual exclusive și numărători private.
- [ ] Paginare și ordonare coerentă; păstrează filtrele în navigare.
- [x] Alegerea unei teme dintr-o listă fixă: lila, crem, roz, verde.
- [x] Tema poate fi modificată doar în ciornă; clase CSS din alegeri validate.
- [x] Afișează datele din listă în fusul utilizatorului, nu doar în fusul global Django.
- [ ] Teste pentru filtre, paginare și fusul orar.

### 7. Cont, parole și notificări

- [ ] Setări profil: nume, fus orar validat și preferință email.
- [ ] Resetare parolă prin email și template-uri coerente vizual.
- [ ] Ștergere cont cu confirmare și eliminarea datelor/fișierelor asociate.
- [ ] Definește și implementează verificarea adresei de email înainte de notificări; tratează schimbarea adresei și eventualele duplicate fără pierderea conturilor existente.
- [ ] Comandă Django periodică pentru notificări de deschidere, cu evidență per capsulă și destinatar.
- [ ] Retry pentru erori; limite și idempotență pentru a reduce duplicatele. Preferința dezactivată oprește emailurile.
- [ ] Emailul conține un link, nu conținutul privat al capsulei.
- [ ] Teste pentru resetare, setări, ștergere, notificări scadente, retry și reexecutare.

### 8. Lansare V1

- [ ] UX pentru succes/erori, accesibilitate cu tastatura și layout pe mobil.
- [ ] HTTPS, DEBUG=False, ALLOWED_HOSTS și configurația secretelor pentru producție.
- [ ] PostgreSQL, storage privat persistent și sarcina periodică configurate.
- [ ] Backup pentru DB și fișiere; restaurare verificată.
- [ ] Documentează retenția backup-urilor, limitele stocării și ștergerea datelor.
- [ ] README cu setup reproductibil și configurație email; `.env.example` fără secrete dacă proiectul folosește .env.
- [ ] Testele și verificările de producție relevante trec.

## V2 - Multimedia și organizare

Începe numai după finalizarea V1.

- [ ] CapsuleEntry pentru mai multe scrisori/blocuri ordonate; migrează mesajele existente fără pierderi.
- [ ] Upload audio MP3/M4A și video MP4; redare în browserele vizate.
- [ ] Limite propuse: 20 MB/audio, 100 MB/video, 250 MB total/capsulă.
- [ ] 8-10 întrebări ghidate fixe, opționale.
- [ ] Predicții scrise în ciornă; verdict și comentariu salvate separat după deschidere.
- [ ] Etichete personale și filtrare.
- [ ] Export ZIP după deschidere: HTML lizibil local, fișiere originale și metadate JSON.
- [ ] Protejează exportul și toate tipurile de fișiere prin aceleași reguli de acces.
- [ ] Teste pentru migrare, limite, export complet, permisiuni și blocare.

În afara acestui MVP: transcriere AI, conversie video și editor complex.

## V3 - Capsule comune

- [ ] Mod separat „capsulă comună”, cu dată de deschidere și termen anterior pentru contribuții.
- [ ] Membri autentificați și invitații prin link cu expirare/revocare, distribuit manual de creator.
- [ ] Fiecare vede și editează doar propria contribuție înainte de sigilare/termen.
- [ ] Creatorul vede membrii și stadiul contribuțiilor, fără a citi mesajele altora înainte de deschidere.
- [ ] Creatorul poate sigila numai după termenul contribuțiilor; conținutul rămâne blocat până la opens_at.
- [ ] La deschidere, membrii activi văd contribuțiile și pot exporta; explică acest lucru înainte de participare.
- [ ] Prima deschidere și notificările devin per membru.
- [ ] Înainte de sigilare: retragere sau eliminare membru cu ștergerea contribuției.
- [ ] După sigilare: autorul poate șterge contribuția și se poate retrage, fără a o edita.
- [ ] Creatorul poate șterge întreaga capsulă; explică regula participanților.
- [ ] Teste pentru invitații, apartenență, izolare, retragere, concurență și notificări.

În afara acestui MVP: chat, contribuții fără cont și roluri avansate.

## V4 - Capsule pentru un destinatar

Flux dorit (planificat, neimplementat): creatorul introduce emailul destinatarului și trimite o capsulă. Dacă există deja un cont cu acea adresă verificată, capsula apare direct în secțiunea „Primite”. Dacă destinatarul nu are cont, primește invitația prin email; după înregistrare și verificarea aceleiași adrese, capsula este asociată contului și apare în „Primite”. Afișarea cardului nu deblochează mesajul înainte de termen și nu înlocuiește acceptarea explicită pentru lectură.

- [ ] Asociere cu un cont existent sau creat ulterior prin aceeași adresă verificată, fără potrivire doar după un email neverificat.
- [ ] Card și detalii pentru capsulele primite: expeditor, destinatar, titlu, data trimiterii, data deschiderii și stare; emailul nu include mesajul privat.
- [ ] Teste pentru ambele fluxuri (cont existent/cont nou), email neverificat, adrese duplicate și izolarea accesului.

- [ ] Mod „pentru cineva”, cu un singur destinatar adult; alternativ la modul comun.
- [ ] Emailul destinatarului poate fi corectat numai înainte de sigilare.
- [ ] La termen: invitație prin email, autentificare și verificarea exactă a adresei vizate.
- [ ] Acceptare explicită; simpla posesie a linkului nu oferă acces.
- [ ] Secțiune „Primite”, lectură și export după acceptare.
- [ ] Stări pentru creator: programată, notificată, acceptată, refuzată; fără confirmare de lectură.
- [ ] Tokenuri expirabile, revocabile și de unică folosință; retrimitere limitată.
- [ ] Refuz și blocarea invitațiilor viitoare de la expeditor.
- [ ] Răspunsul destinatarului este privat implicit; trimiterea către creator este explicită.
- [ ] Creatorul poate șterge capsula inclusiv după acceptare; destinatarul este informat și poate exporta la termen.
- [ ] Teste pentru revendicare cu email greșit, tokenuri, acceptare, refuz și blocare.

În afara acestui MVP: destinatari multipli, conturi pentru minori și deblocare pe baza unor evenimente externe.

## Preferințe UI de păstrat

### Personalitatea aplicației - implementată

Căutarea este în dreapta filtrelor pe desktop, cu buton discret de tip lupă și etichetă accesibilă. Sub 1000px se așază sub filtre pentru a evita înghesuirea.

Căutarea este live: după 300ms de la tastare actualizează cardurile și numărătorile fără reîncărcare. Păstrează focusul și filtrul selectat, anulează cererile vechi și ignoră răspunsurile întârziate. Filtrele și resetarea funcționează tot fără reîncărcare; URL-ul reflectă selecția curentă. Starea căutării este anunțată pentru cititoarele de ecran. Fără JavaScript rămân funcționale formularul GET și linkurile normale. Verificare manuală: tastare rapidă, ștergerea textului, schimbarea filtrului, resetare și conexiune întreruptă.

Implementat pe `feature/capsule-personality`, după popularea cu date demo:

- [x] Previzualizare discretă de plic pe card, adaptată stării capsulei.
- [x] Teme lila, crem, roz și verde, alese prin buline în formular; tema colorează cardul, starea rămâne în badge.
- [x] Formular cu „Despre capsulă” în stânga, „Scrisoarea ta” în dreapta și explicația „Când vrei să o redescoperi?” pentru dată.
- [x] Sigilare prin modal cu data aleasă, pictogramă de sigiliu și animație scurtă, respectând regulile V1 de integritate.
- [x] Deschidere ca o scrisoare: suprafață caldă, text lizibil, spațiu generos și data scrierii; conținutul rămâne privat înainte de termen.
- [x] Căutare în colecție după titlu și descriere, limitată la capsulele proprietarului; păstrează căutarea când schimbi filtrul.

Migrarea `0002_capsule_theme` adaugă tema cu valoarea implicită lila fără pierderea datelor existente; rulează `python manage.py migrate` după actualizare. Validare: 66 de teste Django (11 noi pentru teme, căutare, sigilare, Admin și conflicte între salvări), `make check`, sintaxa JavaScript și verificarea migrărilor. Testele au fost rulate pe SQLite; PostgreSQL nu a fost disponibil local. Încercarea de captură cu Edge headless nu a produs o imagine; aspectul desktop/mobil, blurul și animațiile rămân de verificat manual în browser.

### Date demo locale

Rulează `python manage.py seed_demo` pentru utilizatorul existent `dianaciodolan`, sau `python manage.py seed_demo --username NUME` pentru alt cont existent. Comanda nu creează conturi și nu schimbă parolele. Adaugă 24 de capsule (6 în fiecare stare), cu identificatori stabili; rerularea nu dublează capsulele și nu suprascrie datele existente sau editările manuale. O capsulă demo ștearsă va fi recreată la rerulare. Datele sunt relative la prima generare; rerularea nu reprogramează capsulele existente.

Scenarii: titlu lung, descriere lungă sau absentă, mesaj gol în ciornă, scrisoare lungă, mesaj scurt, diacritice/emoji, text HTML literal, ciornă expirată, termen peste 15 minute, mâine, peste o săptămână, un an și zece ani, capsule disponibile și deschise de mult timp. Datele de creare sunt variate pentru verificarea ordonării. Seed-ul nu generează fotografii sau reflecții. Sigilarea, lectura și fotografiile au acum fluxuri dedicate; reflecțiile rămân neimplementate.

Colecția a fost rafinată pe `feature/collection-ui`: carduri cu înălțimi uniforme pe rând și culori după stare, ștergere în meniul „⋯”, filtre cu numărători, dată relativă plus data exactă în fusul utilizatorului și un mesaj introductiv personal în formular. Notificările se închid după 8 secunde sau manual; temporizatorul se oprește la hover/focus. Validare: 43 de teste Django, verificarea Django și sintaxa JavaScript. Verificarea vizuală/interactivă în browser rămâne manuală.

Modalele folosesc un fundal cu blur de 18px (fallback prin filtrarea paginii), suprafață crem cu accent lila și animație scurtă la apariție (dezactivată pentru `prefers-reduced-motion`). Formularul are un layout orizontal de maximum 1120px, cu mesajul în coloana mai lată și spațiere verticală compactă. Conturul nativ al dialogului și separatorul acțiunilor sunt eliminate; focusul de tastatură rămâne vizibil. Pe ecrane mici se păstrează accesul prin scroll dacă este necesar.

Actualizare UI pe `feature/capsule-ui`: adăugarea, editarea și confirmarea ștergerii se deschid în popup din colecție, fără schimbarea paginii. Escape, închiderea și anularea păstrează colecția; fără JavaScript rămân disponibile rutele normale. Formularul folosește două coloane pe desktop, fără card interior. Pe mobil sau la zoom este permis scroll-ul pentru a păstra toate câmpurile accesibile. Succesul ștergerii apare ca notificare stilizată.

Verificări UI: `node --check static/js/capsules.js`, `make check` și cele 39 de teste Django trec. Verificarea interactivă în browser rămâne manuală: popup de creare/editare, erori de validare, anulare, Escape, focus la închidere, ștergere și notificare; verifică la 1366×768 și pe mobil. Nu a fost confirmată vizual lipsa scroll-ului pe toate dimensiunile.

- Fundal crem și accente lila.
- Text fin, titluri moderate; evită fonturile excesiv de groase sau mari.
- Header transparent și compact.
- Carduri rotunjite, umbre și hover discret.
- Spațiu redus între header și conținut.
- Butonul „Capsulă nouă” în dreapta textului colecției pe desktop, dedesubt pe mobil.
- Texte ale interfeței în română.
- Reorganizează regulile CSS duplicate doar în zona modificată; evită adăugarea continuă a unor override-uri contradictorii.

## Workflow pentru Codex

1. Citește README și orice AGENTS.md aplicabil. Inspectează `git status`, branch-ul, codul și testele relevante.
2. Verifică stadiul real. Dacă ceva este deja implementat, validează-l și actualizează checklist-ul.
3. Lucrează la o singură funcționalitate V1 într-un pas, în ordinea de mai sus. Nu implementa toate versiunile într-o singură sesiune fără solicitare explicită.
4. Păstrează schimbările utilizatorului și evită refactorizările largi. Nu șterge baza de date sau migrările pentru a rezolva erori.
5. Lucrează pe branch-uri dedicate funcționalităților, niciodată direct pe `dev`. Păstrează modificările nesalvate la schimbarea branch-ului.
6. Adaugă teste de comportament și securitate relevante. Nu elimina sau slăbi teste pentru a obține verde.
7. Rulează `make check`, testele relevante și `make test` înainte de finalizare. Dacă make lipsește, folosește comenzile Django echivalente.
8. Pentru modele modificate, creează migrări și verifică `python manage.py makemigrations --check --dry-run`.
9. Pentru UI, verifică pagina pe desktop și mobil dacă ai acces la browser; altfel oferă pași de verificare și declară limita.
10. Marchează o funcționalitate cu [x] numai după implementare și validare; notează separat limitările sau configurarea externă rămasă.
11. Rezumă ce s-a schimbat, fișierele relevante, testele rulate și rezultatele reale. Nu pretinde rulări care nu au avut loc.
12. Conform fluxului cerut în conversație: după finalizarea și verificarea unei funcționalități, fă commit pe branch-ul dedicat și merge local în `dev`; creează următorul branch din `dev`. Push și deploy numai la cerere explicită.

## Definition of done pentru fiecare feature

- Comportamentul și erorile sunt implementate conform checklist-ului.
- Permisiunile sunt verificate pe server pentru GET și POST, unde se aplică.
- CSRF este păstrat; conținutul blocat nu este expus.
- Datele existente și migrările sunt păstrate.
- Testele relevante și suita existentă trec.
- Interfața respectă stilul existent și funcționează pe mobil.
- Checklist-ul și instrucțiunile de configurare sunt actualizate.
