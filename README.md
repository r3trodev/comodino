# Comodino

Stazione meteo, sveglia e calendario Google per il **Chuwi Hi10 Pro**, distribuita come
ISO Debian che si avvia direttamente nell'interfaccia: niente desktop e niente login.

```
┌──────────────────────────────┬───────────────────────────────┐
│                              │  ☀️ 14°  Sereno        Roma   │
│          07:42               │  prossime ore · prossimi gg   │
│    Lunedì 16 novembre        ├───────────────────────────────┤
│                              │  📅 Agenda                    │
│   ⏰ 07:00 · Lun–Ven          │  Oggi    09:30  Lezione       │
│                              │  Domani  Tutto il giorno ...  │
└──────────────────────────────┴───────────────────────────────┘
```

Di notte (orario configurabile) restano solo l'orologio, la sveglia e la temperatura, in
rosso scuro, con la retroilluminazione al minimo. Un tocco riaccende lo schermo per 20 secondi.

## Architettura

| Componente | Cosa fa |
|---|---|
| `comodino/alarmd.py` | **Demone sveglia** (servizio systemd utente). Suona con volume crescente, snooze, spegnimento automatico. È indipendente dalla UI: se l'interfaccia va in crash, la sveglia suona lo stesso. |
| `comodino/ui.py` + `qml/` | Interfaccia PySide6/QML a tutto schermo. Parla col demone su `127.0.0.1:47654` (JSON). |
| `comodino/weather.py` | Meteo da Open-Meteo (gratuito, senza chiave API). |
| `comodino/icsparse.py` | Calendario Google dal link iCal privato. Gestisce eventi ricorrenti, eccezioni, istanze modificate e fusi orari. |
| `system/` | Kiosk: login automatico su tty1, poi `cage` (compositor Wayland a una sola app), regola udev per la luminosità e SSH solo con chiave. |
| `iso/` | Configurazione **live-build** per generare la ISO, con installer sull'eMMC. |

Nella schermata della sveglia, **Rimanda** è un pulsante enorme. Per **spegnere** invece
bisogna tenere premuto 1,5 secondi, così da mezzo addormentati non la spegni per sbaglio.

## 1. Provala sul PC (Windows)

```powershell
pip install PySide6 python-dateutil tzdata
copy config.example.toml config.toml     # e compilalo
python -m comodino.alarmd                 # terminale 1
python -m comodino.ui --dev               # terminale 2 (finestra 1280x800)
```

Il link del calendario lo trovi in Google Calendar → Impostazioni → il tuo calendario →
*Integra calendario* → **Indirizzo segreto in formato iCal**. Chi ha quel link può leggere il
calendario: tienilo solo in `config.toml`, che è escluso da git.

## 2. Verifica l'hardware del tablet (prima di tutto)

Avvia una live Debian trixie qualsiasi da chiavetta e controlla:

- **Boot**: il firmware è UEFI a 64 bit con un menu Windows/Android integrato. La voce "Android"
  avvia `\EFI\BOOT\BOOTX64.EFI`: l'installer ci mette GRUB (senza `fbx64.efi`, che causerebbe un
  bootloop), quindi qualunque voce scelga il menu parte Comodino.
- **Audio**: `speaker-test -c2 -t wav`. Senza audio non c'è sveglia. In caso di problemi usa
  uno speaker USB o Bluetooth.
- **Touch**: `sudo dmesg | grep -i -E "goodix|silead"`. Con Silead serve un file di firmware
  dedicato in `/lib/firmware/silead/`; con Goodix di solito funziona subito.
- **Rotazione**: si sistema dal pannello (⚙️ → Schermo); la rotazione la fa l'interfaccia, quindi il touch resta allineato.

## 3. Genera la ISO

Ti serve una macchina Debian come host di build: una VM sul Proxmox va benissimo.

```bash
cp config.example.toml config.toml                        # compila
cp secrets/wifi.nmconnection.example secrets/wifi.nmconnection   # opzionale: Wi-Fi già configurato
cat ~/.ssh/id_ed25519.pub > secrets/authorized_keys      # opzionale: SSH di manutenzione
cd iso && sudo ./build.sh
```

Il risultato è `iso/live-image-amd64.hybrid.iso`. Scrivila su chiavetta con Rufus (modalità DD)
o con `dd`. Dal menu di boot puoi:

- **Live**: prova tutto senza toccare il tablet;
- **Install**: installa sull'eMMC. Il partizionamento è manuale di proposito: controlla bene
  quale disco scegli, perché è lì che cancelleresti Windows/Android.

## Pannello impostazioni (⚙️ in basso a sinistra)

| Scheda | Cosa fa |
|---|---|
| 🩺 Stato | Verifica tutto: Wi-Fi, IP, ora NTP, meteo, ogni calendario (n. eventi), servizio sveglia, Home Assistant. Riavvio/spegnimento con doppio tocco. |
| 📶 Wi-Fi | Cerca reti e si connette (NetworkManager); password con tastiera virtuale. |
| 📍 Luogo | Cerca la città (geocoding Open-Meteo) e la imposta per il meteo, fuso orario compreso. |
| 🖥️ Schermo | Rotazione 0/90/180/270, luminosità giorno/notte, orari della modalità notte. |
| 🎨 Tema | Layout Classico o Stazione; 10 temi per il giorno (compreso E-ink) (scuri, Nero OLED, chiari) con anteprima, e stile notte: rosso, ambra, grigio o come il tema. |
| 🔋 Batteria | Stato, temperatura, soglie (default 40–80%), scelta della presa smart da Home Assistant, test accendi/spegni. |
| 🏠 Casa | Stato di Home Assistant e delle entità scelte, accendi/spegni. |
| 💻 Da PC | Attiva per 15 minuti una pagina web sulla rete di casa, protetta da PIN mostrato sul tablet, per incollare link iCal, token e entità di Home Assistant. Dopo 5 PIN sbagliati si spegne; il token non viene mai rimandato al browser. |

Le modifiche dal pannello vanno in `~/.local/state/comodino/impostazioni.json` (permessi 600)
e hanno la precedenza su `/etc/comodino/config.toml`.

### Termometro di casa (es. 433 MHz con RFLink su Home Assistant)
Se in «Da PC» è impostato un sensore di temperatura esterno, il Comodino mostra la temperatura
**misurata** al posto di quella di Open-Meteo (che resta visibile, piccola, come «modello»).
Se il sensore non trasmette da più di un'ora si torna alla previsione. La pila del termometro
si trova da sola per RFLink (`sensor.xxx_temp` → `sensor.xxx_bat`), oppure si indica a mano;
quando è scarica compare «cambia la pila del termometro».

### Schermo spento di notte
In ⚙️ → 🖥️ Schermo → «Di notte lo schermo: Spento» la retroilluminazione si spegne nella fascia
notturna (luminosità 0 e, se il driver lo consente, `bl_power=4`). Si riaccende per qualche
secondo con un tocco (il primo tocco non arriva ai pulsanti), da sola prima della sveglia con
l'alba simulata, quando suona, e per un minuto quando compare un avviso importante nuovo
(terremoto forte, allerta arancione o rossa).

### Muffa, grafico, terremoti
- **Rischio muffa** (serve il termometro dentro): stima la temperatura dell'angolo più freddo
  del muro (fattore fRsi, UNI EN ISO 13788, scelto in «Da PC» come isolamento scarso/medio/buono)
  e l'umidità che l'aria della stanza avrebbe lì: sotto 70% ok, 70–80% arieggia, oltre 80%
  rischio muffa, 100% condensa. Con rischio o condensa compare un avviso (solo di giorno).
- **Grafico 24 ore** nel layout Stazione: un punto ogni 10 minuti, salvato in
  `~/.local/state/comodino/storico.json` (fuori: termometro se c'è, altrimenti il modello).
- **Terremoti** dall'INGV (servizio FDSN pubblico): eventi nel raggio e sopra la magnitudo
  scelti in «Da PC» (predefiniti 100 km, M3.0, avviso per 12 ore). In rosso se M≥4.5,
  o M≥3.5 entro 50 km.

### Layout Stazione
Tre colonne più una barra: ora con cifre a 7 segmenti, meteo attuale e max/min, **Fuori/Dentro**
(sensori di Home Assistant, impostabili da «Da PC»; senza sensore esterno si usa Open-Meteo),
alba/tramonto; qualità dell'aria (AQI europeo, PM2.5, polline), vento, direzione, UV, pioggia,
visibilità, pressione; settimana da ieri a +5 giorni. In basso: sveglia, prossimo impegno
dell'agenda e fino a 3 entità di Home Assistant. Di notte si torna alla vista minima.

### Home Assistant
- Le entità scelte compaiono come chip sotto la sveglia; luci e interruttori si accendono/spengono con un tocco.
- La sveglia invia l'evento `comodino_sveglia` con `azione` = `pre` (N minuti prima), `suona`, `rimanda`, `spenta`.
  Esempio di automazione per un'alba simulata:

```yaml
trigger:
  - platform: event
    event_type: comodino_sveglia
    event_data: { azione: pre }
action:
  - service: light.turn_on
    target: { entity_id: light.camera }
    data: { brightness_pct: 100, transition: 900 }   # 15 minuti
```

### Batteria (tablet sempre collegato)
Per non far gonfiare la batteria la si tiene tra `min` e `max` invece che sempre al 100%.
La gestione gira nel demone della sveglia (non si ferma se l'interfaccia si riavvia):

1. **Limite hardware**: se il driver espone `charge_control_end_threshold`, la soglia viene impostata lì.
2. **Presa smart** (caso tipico del Chuwi): sotto il minimo accende la presa del caricatore in
   Home Assistant, sopra il massimo la spegne. Nell'app della presa imposta
   «ripristina stato precedente» dopo un blackout.
3. **Solo lettura**: nessuna presa scelta → solo indicatore e avviso.

Se la batteria scende sotto la soglia di avviso senza caricare, compare un banner rosso (anche di notte).
Su Home Assistant vengono pubblicati `sensor.comodino_batteria` e `sensor.comodino_batteria_temperatura`
(da usare per grafici o notifiche; spariscono se HA si riavvia, finché il tablet non li reinvia).

## Sveglie
- Fino a 10 sveglie con nome, ripetute (giorni scelti) o **una volta sola** (nessun giorno = alla prossima occasione; dopo aver suonato si spegne).
- **Pisolino** 10/20/30 minuti e **alba simulata**: lo schermo passa dal nero al bianco caldo nei minuti prima della sveglia (tocca per nasconderla).
- **Dal telefono** via Home Assistant: crea un helper *Data e/o ora* (es. `input_datetime.sveglia_comodino`, solo ora = ogni giorno, con data = una volta) e, se vuoi, un interruttore `input_boolean.sveglia_comodino`; inseriscili da «Da PC». Il Comodino pubblica `sensor.comodino_prossima_sveglia` (timestamp) da vedere nell'app.

## Meteo extra
- **Pioggia imminente** (Open-Meteo a 15 minuti): «Pioggia tra ~10 min», «Smette di piovere…».
- **Allerte ufficiali** Meteoalarm (gialla/arancione/rossa) per la zona scelta in Luogo → Zona allerte; visibili anche di notte.
- **Fase lunare** calcolata in locale.

## Server Proxmox (sola lettura)
1. In Proxmox: *Datacenter → Permissions → Users* → aggiungi `comodino@pve`; *API Tokens* → aggiungi il token `comodino`
   (con *Privilege Separation*); *Permissions* → aggiungi per il **token** il ruolo **PVEAuditor** sul percorso `/`.
2. Da «Da PC»: indirizzo `https://IP:8006`, token ID `comodino@pve!comodino`, segreto.
3. Sul tablet, scheda 🖧 Server: confronta l'impronta SHA-256 con quella del certificato in Proxmox
   (*nodo → System → Certificates*) e conferma. Da lì in poi ogni certificato diverso viene rifiutato.
Se una VM accesa si ferma, compare un avviso rosso sulla schermata principale.

## Aggiornamenti via GitHub (senza ricompilare la ISO)

Si aggiorna l'**applicazione** (cartella `comodino/`); pacchetti Debian e file di sistema
restano quelli della ISO. Ogni pacchetto è **firmato Ed25519**: il tablet accetta solo
release firmate con la tua chiave privata, solo versioni più nuove, estrae in modo
sicuro, prova il codice prima di attivarlo e, se la nuova versione va in crash 3 volte
appena avviata, torna da solo alla precedente. Il demone sveglia parte con il codice
nuovo solo se si importa senza errori, altrimenti usa quello della ISO.

### Una volta sola
1. Crea un repository su GitHub (es. `utente/comodino`, pubblico) e carica il progetto
   (`config.toml`, `secrets/` e `dist/` sono esclusi da git).
2. Sul PC: `pip install cryptography`, poi `python tools/ota.py chiavi`.
   - `secrets/ota_privata.pem` → cifrata con passphrase, **mai su GitHub**, fanne un backup offline;
   - `system/ota.pub` → fai commit e push: va nella ISO e sul tablet.
3. Primo rilascio (vedi sotto), poi **sul tablet già installato**, da root, una volta:
   ```bash
   python3 -c "R='utente/comodino';import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/'+R+'/main/system/bootstrap.py').read())"
   reboot
   ```
   (Le nuove ISO hanno già tutto: basta `[aggiornamenti] repo = "utente/comodino"` in `config.toml`.)

### Ogni rilascio
```bash
# 1. alza la versione in comodino/__init__.py (es. 0.9.1), commit e push
python tools/ota.py pacchetto            # crea dist/comodino-0.9.1.tar.gz e .sig
gh release create v0.9.1 dist/comodino-0.9.1.tar.gz dist/comodino-0.9.1.tar.gz.sig --notes "Novità…"
```
Sul tablet: ⚙️ → ⬆️ Aggiorna → Controlla → Installa, oppure in automatico tra le 3 e le 5
(mai nell'ora prima di una sveglia). Da lì puoi anche tornare alla versione precedente.

## Manutenzione

- `Ctrl+Alt+F2` apre una console (login root).
- Via SSH: `ssh comodino@<ip-tablet>`, solo se hai messo `secrets/authorized_keys`.
- Log della sveglia: `journalctl --user -u comodino-alarmd` (come utente comodino).
- Configurazione: `/etc/comodino/config.toml`, poi riavvia.

## Note e idee

- Se un nome di pacchetto della lista non esiste più, `lb build` si ferma: controlla con
  `apt search` e correggi `iso/config/package-lists/comodino.list.chroot`.
- Batteria: un tablet sempre in carica rischia di gonfiarsi. Con una presa smart in Home
  Assistant puoi caricarlo solo tra il 30% e l'80%.
- Sviluppi possibili: luci di Home Assistant che si accendono gradualmente prima della sveglia,
  radio in streaming come suono, sensore di temperatura interno via ESP32/MQTT.
