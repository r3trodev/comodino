"""Configurazione da browser (PC o telefono sulla stessa rete).

Serve per le stringhe lunghe, scomode da digitare sul tablet: link iCal, token
di Home Assistant, entità. Sicurezza:
  - si attiva solo dal pannello del tablet e si spegne da sola dopo N minuti;
  - accesso con PIN a 6 cifre mostrato sullo schermo (nuovo a ogni attivazione);
  - dopo 5 PIN sbagliati il server si spegne;
  - il token di Home Assistant non viene mai rimandato al browser.
Nota: è HTTP semplice, pensato per la rete di casa.
"""
import hmac
import json
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from . import config

MAX_TENTATIVI = 5


def campi_modificabili(cfg):
    ha = cfg["homeassistant"]
    return {
        "ics_urls": cfg["calendario"]["ics_urls"],
        "ha_url": ha["url"],
        "ha_token_impostato": bool(ha["token"]),
        "ha_entita": ha["entita"],
        "ha_anticipo_min": ha["anticipo_min"],
        "luogo": cfg["luogo"],
        "clima": cfg["clima"],
        "agg_repo": cfg["aggiornamenti"]["repo"],
        "ha_sveglia_ora": cfg["homeassistant"]["sveglia_ora"],
        "ha_sveglia_attiva": cfg["homeassistant"]["sveglia_attiva"],
        "px_url": cfg["proxmox"]["url"],
        "px_token_id": cfg["proxmox"]["token_id"],
        "px_secret_impostato": bool(cfg["proxmox"]["secret"]),
        "agg_token_impostato": bool(cfg["aggiornamenti"]["token"]),
    }


def valida(data, attuale=None):
    """Controlla i dati in arrivo dal browser; restituisce il dict da salvare."""
    out = {}
    if "ics_urls" in data:
        urls = [u.strip() for u in data["ics_urls"] if u and u.strip()]
        for u in urls:
            if not u.startswith(("https://", "http://", "webcal://")):
                raise ValueError(f"link calendario non valido: {u[:40]}…")
        out["calendario"] = {"ics_urls": urls}
    ha = {}
    if "ha_url" in data:
        u = data["ha_url"].strip().rstrip("/")
        if u and not u.startswith(("http://", "https://")):
            raise ValueError("l'indirizzo di Home Assistant deve iniziare con http:// o https://")
        ha["url"] = u
    if data.get("ha_token"):
        ha["token"] = data["ha_token"].strip()
    if data.get("ha_cancella_token"):
        ha["token"] = ""
    if "ha_entita" in data:
        ents = [e.strip() for e in data["ha_entita"] if e and e.strip()]
        for e in ents:
            if "." not in e or " " in e:
                raise ValueError(f"entità non valida: {e}")
        ha["entita"] = ents
    if "ha_anticipo_min" in data:
        a = int(data["ha_anticipo_min"])
        if not 0 <= a <= 120:
            raise ValueError("anticipo tra 0 e 120 minuti")
        ha["anticipo_min"] = a
    for campo, chiave in (("ha_sveglia_ora", "sveglia_ora"), ("ha_sveglia_attiva", "sveglia_attiva")):
        if campo in data:
            e = data[campo].strip()
            if e and ("." not in e or " " in e):
                raise ValueError(f"entità non valida: {e}")
            ha[chiave] = e
    if ha:
        out["homeassistant"] = ha
    px = {}
    if "px_url" in data:
        u = data["px_url"].strip().rstrip("/")
        if u and not u.startswith("https://"):
            raise ValueError("l'indirizzo di Proxmox deve iniziare con https://")
        px["url"] = u
        if attuale is None or attuale["proxmox"]["url"] != u:
            px["fingerprint"] = ""      # nuovo indirizzo: il certificato va riconfermato
    if "px_token_id" in data:
        t = data["px_token_id"].strip()
        if t and not re.fullmatch(r"[\w.-]+@[\w.-]+![\w.-]+", t):
            raise ValueError("token ID non valido: formato utente@realm!nome")
        px["token_id"] = t
    if data.get("px_secret"):
        px["secret"] = data["px_secret"].strip()
    if px:
        out["proxmox"] = px
    if "clima" in data:
        cl = {}
        for k in ("interno_temp", "interno_umidita", "esterno_temp", "esterno_umidita"):
            v = (data["clima"].get(k) or "").strip()
            if v and ("." not in v or " " in v):
                raise ValueError(f"sensore non valido: {v}")
            cl[k] = v
        out["clima"] = cl
    agg = {}
    if "agg_repo" in data:
        r = data["agg_repo"].strip()
        if r and not re.fullmatch(r"[\w.-]+/[\w.-]+", r):
            raise ValueError("repository non valido: usa il formato utente/progetto")
        agg["repo"] = r
    if data.get("agg_token"):
        agg["token"] = data["agg_token"].strip()
    if data.get("agg_cancella_token"):
        agg["token"] = ""
    if agg:
        out["aggiornamenti"] = agg
    return out


class WebConfig:
    def __init__(self, on_saved, on_state=None):
        self.on_saved = on_saved          # chiamata dopo un salvataggio
        self.on_state = on_state or (lambda: None)
        self.httpd = None
        self.pin = ""
        self.sessioni = set()
        self.tentativi = 0
        self.scade = 0.0
        self.porta = 0
        self._timer = None

    @property
    def attivo(self):
        return self.httpd is not None

    def start(self, porta, minuti):
        self.stop()
        self.pin = f"{secrets.randbelow(10 ** 6):06d}"
        self.sessioni = set()
        self.tentativi = 0
        self.porta = porta
        self.httpd = ThreadingHTTPServer(("0.0.0.0", porta), self._handler())
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.scade = time.time() + minuti * 60
        self._timer = threading.Timer(minuti * 60, self.stop)
        self._timer.daemon = True
        self._timer.start()
        self.on_state()

    def stop(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self.httpd:
            h, self.httpd = self.httpd, None
            threading.Thread(target=h.shutdown, daemon=True).start()
            self.sessioni = set()
            self.on_state()

    # ------------------------------------------------------------ HTTP
    def _handler(self):
        web = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
                data = body.encode() if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def _autenticato(self):
                c = SimpleCookie(self.headers.get("Cookie", ""))
                return "s" in c and c["s"].value in web.sessioni

            def _body(self, limit=64 * 1024):
                n = int(self.headers.get("Content-Length") or 0)
                if n > limit:
                    raise ValueError("richiesta troppo grande")
                return self.rfile.read(n)

            def do_GET(self):
                if self.path == "/":
                    self._send(200, PAGINA if self._autenticato() else LOGIN)
                elif self.path == "/api/config" and self._autenticato():
                    self._send(200, json.dumps(campi_modificabili(config.load())), "application/json")
                else:
                    self._send(404, "non trovato", "text/plain")

            def do_POST(self):
                if self.path == "/login":
                    pin = parse_qs(self._body(1024).decode()).get("pin", [""])[0]
                    if web.pin and hmac.compare_digest(pin.strip(), web.pin):
                        tok = secrets.token_urlsafe(24)
                        web.sessioni.add(tok)
                        self._send(303, "", extra={
                            "Location": "/",
                            "Set-Cookie": f"s={tok}; HttpOnly; SameSite=Strict; Path=/"})
                    else:
                        web.tentativi += 1
                        if web.tentativi >= MAX_TENTATIVI:
                            web.stop()          # prima si disattiva, poi si risponde
                            self._send(403, "Troppi tentativi: configurazione da browser disattivata.", "text/plain")
                            return
                        self._send(401, LOGIN.replace("<!--ERR-->", "<p class=err>PIN errato</p>"))
                elif self.path == "/api/config":
                    if not self._autenticato():
                        return self._send(401, "{}", "application/json")
                    if not self.headers.get("Content-Type", "").startswith("application/json"):
                        return self._send(415, "{}", "application/json")
                    try:
                        cambi = valida(json.loads(self._body()), config.load())
                        config.save_overrides(cambi)
                        web.on_saved()
                        self._send(200, json.dumps({"ok": True}), "application/json")
                    except (ValueError, TypeError) as e:
                        self._send(400, json.dumps({"ok": False, "errore": str(e)}), "application/json")
                else:
                    self._send(404, "non trovato", "text/plain")
        return H


STILE = """<style>
body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;max-width:760px;margin:40px auto;padding:0 16px}
h1{font-weight:600}h2{margin-top:32px;font-size:1.1em;color:#58a6ff}
label{display:block;margin:14px 0 6px;color:#8b949e}
input,textarea{width:100%;box-sizing:border-box;background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:10px;font:inherit}
textarea{min-height:90px;font-family:ui-monospace,monospace;font-size:.9em}
button{margin-top:24px;background:#238636;color:#fff;border:0;border-radius:8px;padding:12px 28px;font:inherit;cursor:pointer}
.hint{font-size:.85em;color:#8b949e}.err{color:#f85149}.ok{color:#3fb950}
</style>"""

LOGIN = f"""<!doctype html><html lang=it><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>Comodino</title>{STILE}<h1>🛏️ Comodino</h1>
<p>Inserisci il PIN mostrato sul tablet (Impostazioni → Da PC).</p><!--ERR-->
<form method=post action=/login><input name=pin inputmode=numeric autocomplete=off maxlength=6 autofocus>
<button>Entra</button></form></html>"""

PAGINA = f"""<!doctype html><html lang=it><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>Comodino – impostazioni</title>{STILE}<h1>🛏️ Comodino – impostazioni</h1>
<h2>📅 Calendari Google</h2>
<label>Indirizzi segreti iCal, uno per riga</label><textarea id=ics></textarea>
<p class=hint>Google Calendar → Impostazioni → il calendario → Integra calendario → <b>Indirizzo segreto in formato iCal</b>.</p>
<h2>🏠 Home Assistant</h2>
<label>Indirizzo</label><input id=haurl placeholder="http://192.168.1.10:8123">
<label>Token di accesso a lunga durata <span id=tokstate class=hint></span></label>
<input id=hatok type=password placeholder="lascia vuoto per non cambiarlo" autocomplete=off>
<p class=hint>Home Assistant → il tuo profilo → Sicurezza → Token di accesso a lunga durata.</p>
<label>Entità da mostrare sul comodino, una per riga</label>
<textarea id=haent placeholder="sensor.temperatura_camera&#10;light.lampada_comodino"></textarea>
<label>Evento "pre" prima della sveglia (minuti, 0 = disattivato)</label><input id=haant type=number min=0 max=120>
<p class=hint>La sveglia invia a Home Assistant l'evento <code>comodino_sveglia</code> con
<code>azione</code> = pre / suona / rimanda / spenta: usalo nelle automazioni (es. luci che si accendono piano).</p>
<h2>🌡️ Sensori dentro / fuori (per il layout Stazione)</h2>
<p class=hint>Entità di Home Assistant (lascia vuoto se non le hai: fuori si usa la previsione di Open-Meteo).</p>
<label>Temperatura dentro</label><input id=it placeholder="sensor.camera_temperatura">
<label>Umidità dentro</label><input id=iu placeholder="sensor.camera_umidita">
<label>Temperatura fuori</label><input id=et placeholder="sensor.balcone_temperatura">
<label>Umidità fuori</label><input id=eu placeholder="sensor.balcone_umidita">
<h2>📱 Sveglia dal telefono (helper di Home Assistant)</h2>
<label>Ora (input_datetime)</label><input id=svora placeholder="input_datetime.sveglia_comodino">
<label>Attiva (input_boolean, opzionale)</label><input id=svatt placeholder="input_boolean.sveglia_comodino">
<h2>🖧 Server Proxmox (sola lettura)</h2>
<label>Indirizzo</label><input id=pxurl placeholder="https://192.168.1.5:8006">
<label>Token ID</label><input id=pxtid placeholder="comodino@pve!comodino">
<label>Segreto del token <span id=pxsec class=hint></span></label>
<input id=pxsecret type=password placeholder="lascia vuoto per non cambiarlo" autocomplete=off>
<h2>⬆️ Aggiornamenti da GitHub</h2>
<label>Repository</label><input id=repo placeholder="utente/comodino">
<label>Token (solo per repository privati) <span id=aggtok class=hint></span></label>
<input id=aggtoken type=password placeholder="lascia vuoto per non cambiarlo" autocomplete=off>
<button onclick=salva()>Salva</button> <span id=msg></span>
<script>
const $=id=>document.getElementById(id);
const righe=t=>t.split('\\n').map(s=>s.trim()).filter(Boolean);
fetch('/api/config').then(r=>r.json()).then(c=>{{
  $('ics').value=c.ics_urls.join('\\n');$('haurl').value=c.ha_url;
  $('haent').value=c.ha_entita.join('\\n');$('haant').value=c.ha_anticipo_min;
  $('tokstate').textContent=c.ha_token_impostato?'(già impostato)':'(non impostato)';
  $('it').value=c.clima.interno_temp;$('iu').value=c.clima.interno_umidita;
  $('et').value=c.clima.esterno_temp;$('eu').value=c.clima.esterno_umidita;
  $('repo').value=c.agg_repo;$('svora').value=c.ha_sveglia_ora;$('svatt').value=c.ha_sveglia_attiva;
  $('pxurl').value=c.px_url;$('pxtid').value=c.px_token_id;$('pxsec').textContent=c.px_secret_impostato?'(già impostato)':'';$('aggtok').textContent=c.agg_token_impostato?'(già impostato)':'';
}});
function salva(){{
  const d={{ics_urls:righe($('ics').value),ha_url:$('haurl').value,ha_entita:righe($('haent').value),
           ha_anticipo_min:parseInt($('haant').value||'0'),
           clima:{{interno_temp:$('it').value,interno_umidita:$('iu').value,
                   esterno_temp:$('et').value,esterno_umidita:$('eu').value}},
           agg_repo:$('repo').value,ha_sveglia_ora:$('svora').value,ha_sveglia_attiva:$('svatt').value,
           px_url:$('pxurl').value,px_token_id:$('pxtid').value}};
  if($('pxsecret').value)d.px_secret=$('pxsecret').value;
  if($('aggtoken').value)d.agg_token=$('aggtoken').value;
  if($('hatok').value)d.ha_token=$('hatok').value;
  fetch('/api/config',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(d)}})
   .then(r=>r.json()).then(r=>{{$('msg').className=r.ok?'ok':'err';
     $('msg').textContent=r.ok?'Salvato ✓ (il tablet si aggiorna da solo)':r.errore;
     if(r.ok){{$('hatok').value='';$('tokstate').textContent=d.ha_token?'(già impostato)':$('tokstate').textContent}}}});
}}
</script></html>"""
