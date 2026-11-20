"""Test della logica senza interfaccia: python3 -m unittest discover tests"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()

from comodino import alarmd, icsparse, weather  # noqa: E402

TZ = ZoneInfo("Europe/Rome")

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART;TZID=Europe/Rome:20261116T093000
DTEND;TZID=Europe/Rome:20261116T110000
SUMMARY:Lezione di Analisi
LOCATION:Aula 3\\, Edificio B
UID:single@test
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261117
DTEND;VALUE=DATE:20261118
SUMMARY:Compleanno
UID:allday@test
END:VEVENT
BEGIN:VEVENT
DTSTART:20261110T170000Z
DTEND:20261110T180000Z
RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20261231T235959Z
EXDATE:20261124T170000Z
SUMMARY:Palestra
UID:weekly@test
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Promemoria
TRIGGER:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Rome:20261101T080000
DTEND;TZID=Europe/Rome:20261101T081500
RRULE:FREQ=DAILY;UNTIL=20261130
SUMMARY:Medicina
UID:daily@test
END:VEVENT
BEGIN:VEVENT
RECURRENCE-ID;TZID=Europe/Rome:20261118T080000
DTSTART;TZID=Europe/Rome:20261118T090000
DTEND;TZID=Europe/Rome:20261118T091500
SUMMARY:Medicina (spostata)
UID:daily@test
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Rome:20261119T120000
DTEND;TZID=Europe/Rome:20261119T130000
SUMMARY:Annullato
STATUS:CANCELLED
UID:cancel@test
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261114
DTEND;VALUE=DATE:20261117
SUMMARY:Viaggio
UID:multi@test
END:VEVENT
END:VCALENDAR
"""


class TestICS(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 10, 0, tzinfo=TZ)
        start = datetime.combine(self.now.date(), time(0), TZ)
        self.items = icsparse.occurrences(icsparse.parse(ICS, TZ), start, start + timedelta(days=16), TZ)
        self.titles = [(i["inizio"].astimezone(TZ).strftime("%m-%d %H:%M"), i["titolo"]) for i in self.items]

    def test_single_and_escape(self):
        ev = [i for i in self.items if i["titolo"] == "Lezione di Analisi"][0]
        self.assertEqual(ev["luogo"], "Aula 3, Edificio B")
        self.assertEqual(ev["inizio"].astimezone(TZ).hour, 9)

    def test_weekly_with_exdate(self):
        palestra = [t for t, n in self.titles if n == "Palestra"]
        # 17/11 e 1/12 (il 24/11 è escluso); 17:00Z = 18:00 a Roma
        self.assertEqual(palestra, ["11-17 18:00", "12-01 18:00"])

    def test_daily_override_and_until(self):
        med = [t for t, n in self.titles if n.startswith("Medicina")]
        self.assertIn("11-18 09:00", med)
        self.assertNotIn("11-18 08:00", med)
        self.assertEqual(med[-1], "11-30 08:00")    # UNTIL in formato data

    def test_cancelled_and_allday(self):
        names = [n for _, n in self.titles]
        self.assertNotIn("Annullato", names)
        self.assertIn("Compleanno", names)
        self.assertIn("Viaggio", names)             # iniziato prima, ancora in corso

    def test_agenda(self):
        rows = icsparse.agenda(self.items, self.now, TZ)
        self.assertEqual(rows[0]["giorno"], "Oggi")
        self.assertEqual(rows[0]["titolo"], "Viaggio")   # tutto il giorno prima degli orari
        oggi = [r for r in rows if r["giorno"] == "Oggi"]
        stato = {r["titolo"]: r["passato"] for r in oggi}
        self.assertTrue(stato["Medicina"])               # 08:00-08:15, già passata alle 10
        self.assertFalse(stato["Lezione di Analisi"])    # 09:30-11:00, in corso
        self.assertTrue(any(r["giorno"] == "Domani" for r in rows))
        self.assertIn("Mercoledì 18 novembre", {r["giorno"] for r in rows})


class TestWeather(unittest.TestCase):
    def test_parse(self):
        hours = [f"2026-11-16T{h:02d}:00" for h in range(24)]
        days = [f"2026-11-{d}" for d in range(16, 21)]
        data = {
            "current": {"temperature_2m": 13.6, "apparent_temperature": 12.1,
                        "relative_humidity_2m": 71, "weather_code": 2,
                        "wind_speed_10m": 9.4, "is_day": 1},
            "hourly": {"time": hours, "temperature_2m": [10 + h / 4 for h in range(24)],
                       "weather_code": [61] * 24, "precipitation_probability": [40] * 24,
                       "is_day": [1 if 7 <= h < 17 else 0 for h in range(24)]},
            "daily": {"time": days, "weather_code": [0, 3, 63, 95, 71],
                      "temperature_2m_max": [16, 15, 12, 11, 4],
                      "temperature_2m_min": [8, 7, 6, 5, -1],
                      "precipitation_probability_max": [0, 10, 80, 90, 60],
                      "sunrise": [d + "T07:04" for d in days],
                      "sunset": [d + "T16:47" for d in days]},
        }
        out = weather.parse(data, now=datetime(2026, 11, 16, 10, 25))
        self.assertEqual(out["temp"], 14)
        self.assertEqual(out["descrizione"], "Parzialmente nuvoloso")
        self.assertEqual([o["ora"] for o in out["ore"]], ["11", "12", "13", "14", "15", "16"])
        self.assertEqual([g["nome"] for g in out["giorni"]], ["Oggi", "Mar", "Mer", "Gio"])
        self.assertEqual(out["alba"], "07:04")


# ---------------------------------------------------------------- v0.2: pannello impostazioni
from comodino import config, geocode, sistema, webconfig  # noqa: E402


class TestConfig(unittest.TestCase):
    def test_overrides_and_rotation(self):
        config.overrides_path().unlink(missing_ok=True)
        config.save_overrides({"schermo": {"rotazione": "270"}, "luogo": {"nome": "Napoli"}})
        config.save_overrides({"luogo": {"lat": 40.85}})
        cfg = config.load()
        self.assertEqual(cfg["schermo"]["rotazione"], 270)
        self.assertEqual((cfg["luogo"]["nome"], cfg["luogo"]["lat"]), ("Napoli", 40.85))
        self.assertEqual(cfg["luogo"]["fuso"], "Europe/Rome")      # default conservato
        self.assertEqual(config.rotation_degrees("normal"), 0)
        config.overrides_path().unlink()


class TestWifi(unittest.TestCase):
    def test_terse(self):
        self.assertEqual(sistema.split_terse(r"*:Casa\:5G:78:WPA2"), ["*", "Casa:5G", "78", "WPA2"])

    def test_list(self):
        out = "\n".join([":Vicino:40:WPA2", "*:Casa:70:WPA2", ":Casa:55:WPA2", ":Ospiti:90:", "::30:WPA2"])
        reti = sistema.parse_wifi_list(out)
        self.assertEqual([r["ssid"] for r in reti], ["Casa", "Ospiti", "Vicino"])
        self.assertTrue(reti[0]["attiva"])
        self.assertEqual(reti[0]["segnale"], 70)
        self.assertFalse(reti[1]["protetta"])


class TestGeocode(unittest.TestCase):
    def test_parse(self):
        r = geocode.parse({"results": [{"name": "Lecce", "admin1": "Puglia", "admin2": "Lecce",
                                        "country": "Italia", "latitude": 40.35234,
                                        "longitude": 18.16918, "timezone": "Europe/Rome"}]})
        self.assertEqual(r[0], {"nome": "Lecce", "dettaglio": "Lecce, Puglia, Italia",
                                "lat": 40.3523, "lon": 18.1692, "fuso": "Europe/Rome"})
        self.assertEqual(geocode.parse({}), [])


class TestWebConfig(unittest.TestCase):
    def test_valida(self):
        out = webconfig.valida({"ics_urls": ["https://a/b.ics", " "], "ha_url": "http://ha:8123/",
                                "ha_token": " abc ", "ha_entita": ["light.x"], "ha_anticipo_min": "10"})
        self.assertEqual(out["calendario"]["ics_urls"], ["https://a/b.ics"])
        self.assertEqual(out["homeassistant"], {"url": "http://ha:8123", "token": "abc",
                                                "entita": ["light.x"], "anticipo_min": 10})
        self.assertNotIn("token", webconfig.valida({"ha_token": ""}).get("homeassistant", {}))
        for bad in ({"ics_urls": ["file:///etc/passwd"]}, {"ha_url": "ftp://x"},
                    {"ha_entita": ["luce cucina"]}, {"ha_anticipo_min": 500}):
            with self.assertRaises(ValueError):
                webconfig.valida(bad)

    def test_http_flow(self):
        import http.client
        import json as _json
        config.overrides_path().unlink(missing_ok=True)
        saved = []
        w = webconfig.WebConfig(on_saved=lambda: saved.append(1))
        w.start(0, 1)
        port = w.httpd.server_address[1]

        def req(method, path, body=None, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            c.request(method, path, body=body, headers=headers or {})
            r = c.getresponse()
            data = r.read()
            c.close()
            return r, data

        r, _ = req("GET", "/api/config")
        self.assertEqual(r.status, 404)                      # non autenticato
        r, _ = req("POST", "/login", "pin=000000" if w.pin != "000000" else "pin=111111")
        self.assertEqual(r.status, 401)
        r, _ = req("POST", "/login", f"pin={w.pin}")
        self.assertEqual(r.status, 303)
        cookie = r.getheader("Set-Cookie").split(";")[0]
        r, data = req("GET", "/api/config", headers={"Cookie": cookie})
        self.assertEqual(r.status, 200)
        self.assertFalse(_json.loads(data)["ha_token_impostato"])
        body = _json.dumps({"ha_url": "http://ha.local:8123", "ha_token": "segreto"})
        r, _ = req("POST", "/api/config", body, {"Cookie": cookie, "Content-Type": "application/json"})
        self.assertEqual(r.status, 200)
        self.assertEqual(saved, [1])
        r, data = req("GET", "/api/config", headers={"Cookie": cookie})
        self.assertTrue(_json.loads(data)["ha_token_impostato"])
        self.assertNotIn(b"segreto", data)                   # il token non torna mai al browser
        r, _ = req("POST", "/api/config", body, {"Cookie": cookie, "Content-Type": "text/plain"})
        self.assertEqual(r.status, 415)
        w.stop()
        config.overrides_path().unlink()

    def test_lockout(self):
        import http.client
        w = webconfig.WebConfig(on_saved=lambda: None)
        w.start(0, 1)
        port = w.httpd.server_address[1]
        wrong = "000000" if w.pin != "000000" else "111111"
        for _ in range(webconfig.MAX_TENTATIVI):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            c.request("POST", "/login", f"pin={wrong}")
            c.getresponse().read()
            c.close()
        self.assertFalse(w.attivo)


# ---------------------------------------------------------------- v0.3: batteria
from comodino import batteria  # noqa: E402


def fake_sysfs(cap=55, status="Discharging", online="0", soglia=None, temp="312"):
    from pathlib import Path
    root = Path(tempfile.mkdtemp())
    b = root / "axp288_fuel_gauge"
    b.mkdir()
    for k, v in {"type": "Battery", "capacity": str(cap), "status": status, "present": "1",
                 "health": "Good", "temp": temp}.items():
        (b / k).write_text(v + "\n")
    if soglia is not None:
        (b / "charge_control_end_threshold").write_text(str(soglia))
    c = root / "axp288_charger"
    c.mkdir()
    (c / "type").write_text("USB\n")
    (c / "online").write_text(online + "\n")
    hid = root / "hid-mouse-battery"          # batteria di un mouse: va ignorata
    hid.mkdir()
    (hid / "type").write_text("Battery\n")
    (hid / "scope").write_text("Device\n")
    return root


class FakeHA:
    configurato = True

    def __init__(self):
        self.cmds, self.sensori = [], []

    def accendi(self, eid, on):
        self.cmds.append((eid, on))

    def imposta_stato(self, eid, stato, attr):
        self.sensori.append((eid, stato))


def full_cfg(**batt):
    import copy
    c = copy.deepcopy(config.DEFAULT)
    c["batteria"].update(batt)
    return c


class TestBatteria(unittest.TestCase):
    def test_leggi(self):
        b = batteria.leggi(fake_sysfs(cap=63, status="Charging", online="1"))
        self.assertTrue(b["presente"])
        self.assertEqual((b["nome"], b["percentuale"], b["alimentato"]), ("axp288_fuel_gauge", 63, True))
        self.assertEqual((b["stato_it"], b["temperatura"], b["soglia_kernel"]), ("In carica", 31.2, ""))
        self.assertFalse(batteria.leggi("/percorso/inesistente")["presente"])

    def test_decidi(self):
        self.assertEqual(batteria.decidi(40, False, 40, 80), "on")
        self.assertEqual(batteria.decidi(80, True, 40, 80), "off")
        self.assertIsNone(batteria.decidi(60, True, 40, 80))     # in carica verso l'80: lascia stare
        self.assertIsNone(batteria.decidi(60, False, 40, 80))    # a batteria verso il 40: lascia stare
        self.assertIsNone(batteria.decidi(None, False, 40, 80))

    def test_presa(self):
        root = fake_sysfs(cap=38, online="0")
        m = batteria.BatteryManager(full_cfg(presa="switch.presa_comodino"), root)
        m.ha = FakeHA()
        m.tick()
        self.assertEqual(m.ha.cmds, [("switch.presa_comodino", True)])
        self.assertEqual(m.stato["metodo"], "presa")
        self.assertIn(("sensor.comodino_batteria", 38), m.ha.sensori)
        m.tick()                                    # nessuna ripetizione immediata
        self.assertEqual(len(m.ha.cmds), 1)
        (root / "axp288_fuel_gauge" / "capacity").write_text("81")
        (root / "axp288_charger" / "online").write_text("1")
        m.tick()
        self.assertEqual(m.ha.cmds[-1], ("switch.presa_comodino", False))
        self.assertIn("spenta", m.stato["azione"])

    def test_avviso_e_lettura(self):
        m = batteria.BatteryManager(full_cfg(), fake_sysfs(cap=15, online="0"))
        m.tick()                                    # nessuna presa né HA: solo lettura
        self.assertEqual(m.stato["metodo"], "lettura")
        self.assertTrue(m.stato["avviso"])

    def test_soglia_kernel(self):
        root = fake_sysfs(cap=70, soglia=100)
        m = batteria.BatteryManager(full_cfg(max=80), root)
        m.tick()
        self.assertEqual(m.stato["metodo"], "kernel")
        self.assertEqual((root / "axp288_fuel_gauge" / "charge_control_end_threshold").read_text(), "80")

    def test_stato_in_sveglia(self):
        m = batteria.BatteryManager(full_cfg(), fake_sysfs(cap=50))
        m.tick()
        a = alarmd.Alarm(dict(config.DEFAULT["sveglia"]), None, m)
        self.assertEqual(a.status()["batteria"]["percentuale"], 50)


# ---------------------------------------------------------------- v0.4: correzioni
class TestLocale(unittest.TestCase):
    def test_comandi_in_inglese(self):
        # nmcli localizzato risponderebbe "sì": i comandi devono girare in locale C
        self.assertEqual(sistema._ENV["LC_ALL"], "C")

    def test_wifi_status_parsing(self):
        import unittest.mock as mock
        with mock.patch.object(sistema, "_run", return_value=(0, "no:Vicino:40\nyes:Casa\\:5G:72\n", "")):
            self.assertEqual(sistema.wifi_status(), {"connesso": True, "ssid": "Casa:5G", "segnale": 72})


class TestTemiConfig(unittest.TestCase):
    def test_default(self):
        cfg = config.load()
        self.assertEqual((cfg["schermo"]["tema"], cfg["schermo"]["notte_stile"]), ("notte", "rosso"))


# ---------------------------------------------------------------- v0.5: luminosità
from comodino import luminosita  # noqa: E402


def fake_backlight(*devs):
    from pathlib import Path
    root = Path(tempfile.mkdtemp())
    for nome, tipo, mx in devs:
        d = root / nome
        d.mkdir()
        (d / "type").write_text(tipo + "\n")
        (d / "max_brightness").write_text(f"{mx}\n")
        (d / "brightness").write_text("0\n")
    return root


class TestLuminosita(unittest.TestCase):
    def test_sceglie_driver_nativo(self):
        root = fake_backlight(("acpi_video0", "firmware", 100), ("intel_backlight", "raw", 937))
        b = luminosita.Backlight(base=root)
        self.assertEqual(b.dev.name, "intel_backlight")       # non il primo in ordine alfabetico
        b.set(50)
        self.assertEqual((root / "intel_backlight" / "brightness").read_text(), "468")
        self.assertEqual(b.stato()["metodo"], "sysfs")
        self.assertEqual(b.stato()["alternative"], ["intel_backlight", "acpi_video0"])

    def test_preferito_e_minimo(self):
        root = fake_backlight(("acpi_video0", "firmware", 100), ("intel_backlight", "raw", 937))
        b = luminosita.Backlight("acpi_video0", base=root)
        self.assertEqual(b.dev.name, "acpi_video0")
        b.set(0)
        self.assertEqual((root / "acpi_video0" / "brightness").read_text(), "1")   # mai schermo nero

    def test_fallback_logind(self):
        import os
        root = fake_backlight(("intel_backlight", "raw", 100))
        os.chmod(root / "intel_backlight" / "brightness", 0o444)
        chiamate = []
        b = luminosita.Backlight(base=root, logind=lambda n, v: (chiamate.append((n, v)) or True, ""))
        b.set(30)
        if os.geteuid() != 0:          # da root la scrittura riuscirebbe comunque
            self.assertEqual(chiamate, [("intel_backlight", 30)])
            self.assertEqual(b.stato()["metodo"], "logind")

    def test_errore_visibile(self):
        import os
        root = fake_backlight(("intel_backlight", "raw", 100))
        os.chmod(root / "intel_backlight" / "brightness", 0o444)
        b = luminosita.Backlight(base=root, logind=lambda n, v: (False, "Access denied"))
        b.set(30)
        if os.geteuid() != 0:
            self.assertIn("logind: Access denied", b.stato()["errore"])

    def test_nessun_dispositivo(self):
        b = luminosita.Backlight(base="/percorso/inesistente")
        b.set(50)
        self.assertIn("nessun dispositivo", b.stato()["errore"])


# ---------------------------------------------------------------- v0.6: Wi-Fi dopo password sbagliata
class FakeNM:
    """Simula nmcli: come quello vero, se esiste già un profilo per la rete
    usa la password salvata lì e ignora quella nuova."""

    def __init__(self, reti):
        self.reti = reti            # ssid -> password corretta
        self.profili = {}           # uuid -> (ssid, password salvata)
        self.n = 0

    def __call__(self, args, timeout=20):
        a = [x for x in args if x not in ("--wait", "45")]
        if a[1:4] == ["-t", "-f", "UUID,TYPE"]:
            return 0, "".join(f"{u}:802-11-wireless\n" for u in self.profili), ""
        if a[1] == "-g":
            return 0, self.profili[a[-1]][0] + "\n", ""
        if a[1:3] == ["connection", "delete"]:
            self.profili.pop(a[-1], None)
            return 0, "", ""
        if a[1:4] == ["device", "wifi", "connect"]:
            ssid = a[4]
            pw = a[a.index("password") + 1] if "password" in a else ""
            esistente = next((u for u, (s, _) in self.profili.items() if s == ssid), None)
            if esistente:
                pw = self.profili[esistente][1]          # il bug: riusa la password vecchia
            else:
                self.n += 1
                self.profili[f"uuid-{self.n}"] = (ssid, pw)
            if pw == self.reti.get(ssid):
                return 0, "Device successfully activated", ""
            return 4, "", "Error: Connection activation failed: Secrets were required, but not provided."
        raise AssertionError(a)


class TestWifiRiprova(unittest.TestCase):
    def test_password_sbagliata_poi_giusta(self):
        import unittest.mock as mock
        nm = FakeNM({"Casa": "giusta123"})
        with mock.patch.object(sistema, "_run", nm):
            r1 = sistema.wifi_connect("Casa", "sbagliata")
            self.assertEqual(r1, {"ok": False, "errore": "Password errata"})
            self.assertEqual(nm.profili, {})                 # nessun profilo rotto rimasto
            r2 = sistema.wifi_connect("Casa", "giusta123")
            self.assertTrue(r2["ok"], r2)
            self.assertEqual(len(nm.profili), 1)

    def test_profilo_vecchio_rimosso(self):
        import unittest.mock as mock
        nm = FakeNM({"Casa": "nuova"})
        nm.profili["vecchio"] = ("Casa", "vecchia")          # es. creato da una versione precedente
        nm.profili["altro"] = ("Vicino", "x")
        with mock.patch.object(sistema, "_run", nm):
            self.assertTrue(sistema.wifi_connect("Casa", "nuova")["ok"])
        self.assertIn("altro", nm.profili)                   # le altre reti restano
        self.assertNotIn("vecchio", nm.profili)


# ---------------------------------------------------------------- v0.7: errori calendario leggibili
class TestSpiegaErrore(unittest.TestCase):
    def test_messaggi(self):
        import socket
        import ssl
        import urllib.error
        s = icsparse.spiega_errore
        self.assertIn("link non valido", s(urllib.error.HTTPError("u", 404, "Not Found", {}, None)))
        self.assertIn("DNS", s(urllib.error.URLError(socket.gaierror(-3, "Temporary failure in name resolution"))))
        cert = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate is not yet valid")
        self.assertIn("ora del tablet", s(urllib.error.URLError(cert)))
        self.assertEqual(s(TimeoutError("timed out")), "tempo scaduto")


# ---------------------------------------------------------------- v0.8: layout Stazione
class TestStazione(unittest.TestCase):
    def dati(self):
        days = [f"2026-11-{d}" for d in range(15, 23)]          # 15 = ieri
        hours = [f"2026-11-16T{h:02d}:00" for h in range(24)]
        return {
            "current": {"temperature_2m": 18.64, "apparent_temperature": 18, "relative_humidity_2m": 69,
                        "weather_code": 3, "wind_speed_10m": 11.2, "wind_direction_10m": 177, "is_day": 1,
                        "pressure_msl": 1011.4, "precipitation": 0.2, "uv_index": 2.96, "visibility": 24140},
            "hourly": {"time": hours, "temperature_2m": [15] * 24, "weather_code": [3] * 24,
                       "precipitation_probability": [5] * 24, "is_day": [1] * 24},
            "daily": {"time": days, "weather_code": [61, 3, 2, 3, 2, 0, 95, 80],
                      "temperature_2m_max": [20, 20, 20, 21, 21, 22, 19, 18],
                      "temperature_2m_min": [14, 14, 14, 16, 14, 13, 12, 11],
                      "precipitation_probability_max": [60, 8, 5, 3, 0, 0, 90, 40],
                      "sunrise": [d + "T06:59" for d in days], "sunset": [d + "T16:49" for d in days]},
        }

    def test_parse_extra(self):
        out = weather.parse(self.dati(), now=datetime(2026, 11, 16, 14, 30))
        self.assertEqual((out["direzione"], out["direzione_gradi"]), ("S", 177))
        self.assertEqual((out["pressione"], out["uv"], out["visibilita_km"], out["pioggia_mm"]), (1011, 3.0, ">10", 0.2))
        self.assertEqual(out["temp_decimale"], 18.6)
        self.assertEqual([g["nome"] for g in out["settimana"]], ["Ieri", "Oggi", "Mar", "Mer", "Gio", "Ven", "Sab"])
        self.assertTrue(out["settimana"][0]["passato"])
        self.assertEqual([g["nome"] for g in out["giorni"]], ["Oggi", "Mar", "Mer", "Gio"])
        self.assertEqual(out["alba"], "06:59")                    # di oggi, non di ieri

    def test_direzione(self):
        self.assertEqual([weather.direzione(g) for g in (0, 44, 46, 180, 225, 270, 337, 359)],
                         ["N", "NE", "NE", "S", "SO", "O", "NO", "N"])
        self.assertEqual(weather.direzione(None), "")

    def test_aria(self):
        a = weather.parse_aria({"current": {"european_aqi": 33.4, "pm2_5": 12.2, "grass_pollen": 3.0,
                                            "olive_pollen": 55.0, "birch_pollen": None}})
        self.assertEqual(a, {"aqi": 33, "aqi_testo": "Discreta", "pm25": 12, "polline": "Alto"})
        self.assertEqual(weather.parse_aria({"current": {}})["polline"], "—")
        self.assertEqual(weather.livello_aqi(105), "Pessima")

    def test_web_clima(self):
        out = webconfig.valida({"clima": {"interno_temp": "sensor.camera_t", "esterno_temp": ""}})
        self.assertEqual(out["clima"]["interno_temp"], "sensor.camera_t")
        with self.assertRaises(ValueError):
            webconfig.valida({"clima": {"interno_temp": "camera"}})


# ---------------------------------------------------------------- v0.9: aggiornamenti firmati
import importlib.util as _ilu  # noqa: E402
from comodino import ota  # noqa: E402

_spec = _ilu.spec_from_file_location("ota_tool", os.path.join(os.path.dirname(__file__), "..", "tools", "ota.py"))
ota_tool = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(ota_tool)


class TestOTA(unittest.TestCase):
    PW = "passphrase-di-prova-123"

    def setUp(self):
        import http.server
        import threading
        from functools import partial
        from pathlib import Path
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.dir = Path(tempfile.mkdtemp())
        os.environ["XDG_DATA_HOME"] = str(self.dir / "data")
        k = Ed25519PrivateKey.generate()
        self.priv = self.dir / "priv.pem"
        self.priv.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.BestAvailableEncryption(self.PW.encode())))
        self.pub = self.dir / "ota.pub"
        self.pub.write_bytes(k.public_key().public_bytes(serialization.Encoding.PEM,
                                                         serialization.PublicFormat.SubjectPublicKeyInfo))
        self.www = self.dir / "www"
        self.www.mkdir()
        h = partial(http.server.SimpleHTTPRequestHandler, directory=str(self.www))
        http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        os.environ.pop("XDG_DATA_HOME", None)

    def pubblica(self, ver, tar=None, firma_ok=True):
        nome = f"comodino-{ver}.tar.gz"
        pac = self.www / nome
        if tar:
            tar(pac)
        else:
            ota_tool.crea_tar(pac, ver)
        ota_tool.firma(pac, self.priv, self.PW)
        if not firma_ok:                         # pacchetto modificato dopo la firma
            with open(pac, "ab") as f:
                f.write(b"\0")
        rel = {"tag_name": f"v{ver}", "body": "Novità", "published_at": "2026-11-17T01:00:00Z",
               "assets": [{"name": nome, "browser_download_url": f"{self.url}/{nome}", "size": 1},
                          {"name": nome + ".sig", "browser_download_url": f"{self.url}/{nome}.sig", "size": 64}]}
        return ota.parse_release(rel)

    def installa(self, info, corrente="0.8.1"):
        return ota.installa(info, corrente=corrente, chiave=self.pub)

    def test_installa_e_ripristina(self):
        from pathlib import Path
        self.assertEqual(self.installa(self.pubblica("0.9.0")), "0.9.0")
        att = ota.base_dir() / "attuale"
        self.assertTrue((att / "comodino" / "alarmd.py").is_file())
        self.assertEqual(Path(os.readlink(att)).name, "0.9.0")
        self.assertFalse((ota.base_dir() / "precedente").is_symlink())    # prima: ISO
        self.assertEqual(self.installa(self.pubblica("0.9.1"), corrente="0.9.0"), "0.9.1")
        self.assertEqual(Path(os.readlink(ota.base_dir() / "precedente")).name, "0.9.0")
        self.assertEqual(ota.ripristina(), "0.9.0")
        self.assertEqual(ota.ripristina(), "versione della ISO")
        self.assertFalse(att.is_symlink())

    def test_firma_manomessa(self):
        with self.assertRaisesRegex(ValueError, "FIRMA NON VALIDA"):
            self.installa(self.pubblica("0.9.0", firma_ok=False))
        self.assertFalse((ota.base_dir() / "attuale").exists())

    def test_chiave_diversa(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        altra = self.dir / "altra.pub"
        altra.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        with self.assertRaisesRegex(ValueError, "FIRMA NON VALIDA"):
            ota.installa(self.pubblica("0.9.0"), corrente="0.8.1", chiave=altra)

    def test_niente_downgrade(self):
        with self.assertRaisesRegex(ValueError, "non è più nuova"):
            self.installa(self.pubblica("0.8.1"))

    def test_versione_nel_pacchetto_falsa(self):
        info = self.pubblica("0.9.0")
        info["versione"] = "1.0.0"              # tag manomesso, pacchetto firmato dice 0.9.0
        with self.assertRaisesRegex(ValueError, "contiene la versione 0.9.0"):
            self.installa(info)

    def test_tar_malevolo(self):
        import io
        import tarfile

        def cattivo(dest):
            with tarfile.open(dest, "w:gz") as t:
                for nome, dati in (("VERSION", b"0.9.0\n"), ("../../evil.sh", b"rm -rf /")):
                    ti = tarfile.TarInfo(nome)
                    ti.size = len(dati)
                    t.addfile(ti, io.BytesIO(dati))
        with self.assertRaisesRegex(ValueError, "percorso non ammesso"):
            self.installa(self.pubblica("0.9.0", tar=cattivo))

    def test_codice_rotto(self):
        import tarfile

        def rotto(dest):
            ota_tool.crea_tar(dest, "0.9.0")
            tmp = self.dir / "rotto"
            with tarfile.open(dest) as t:
                t.extractall(tmp, filter="data")
            (tmp / "comodino" / "alarmd.py").write_text("def (:\n")
            with tarfile.open(dest, "w:gz") as t:
                for x in ("comodino", "system", "VERSION"):
                    t.add(tmp / x, arcname=x)
        with self.assertRaisesRegex(RuntimeError, "prova di avvio fallita"):
            self.installa(self.pubblica("0.9.0", tar=rotto))
        self.assertFalse((ota.base_dir() / "attuale").exists())

    def test_versione(self):
        self.assertEqual(ota.versione("v1.2.10"), (1, 2, 10))
        self.assertGreater(ota.versione("0.10.0"), ota.versione("0.9.9"))     # non confronto di stringhe
        with self.assertRaises(ValueError):
            ota.versione("latest")

    def test_web_repo(self):
        self.assertEqual(webconfig.valida({"agg_repo": "mario/comodino"})["aggiornamenti"], {"repo": "mario/comodino"})
        with self.assertRaises(ValueError):
            webconfig.valida({"agg_repo": "https://github.com/x"})



# ---------------------------------------------------------------- v0.9.1: più sveglie, telefono
class TestSveglie(unittest.TestCase):
    def make(self, sveglie=(), **cfg):
        c = dict(alarmd.config.DEFAULT["sveglia"])
        a = alarmd.Alarm(c, cfg or None)
        a.state = {"sveglie": [], "snooze_fino": None}
        for sv in sveglie:
            a.salva_sveglia(sv)
        return a

    def test_piu_sveglie(self):
        a = self.make([{"nome": "Lavoro", "ora": 7, "minuto": 0, "giorni": [0, 1, 2, 3, 4]},
                       {"nome": "Weekend", "ora": 9, "minuto": 30, "giorni": [5, 6]}])
        ven_sera = datetime(2026, 11, 20, 22, 0)
        at, sv = a.prossima(ven_sera)
        self.assertEqual((at, sv["nome"]), (datetime(2026, 11, 21, 9, 30), "Weekend"))
        self.assertEqual(a.prossima(datetime(2026, 11, 16, 6, 0))[1]["nome"], "Lavoro")
        self.assertEqual([x["id"] for x in a.state["sveglie"]], ["1", "2"])

    def test_una_volta_sola(self):
        a = self.make()
        sid = a.salva_sveglia({"nome": "Treno", "ora": 5, "minuto": 40, "data": "2026-11-10"})
        sv = a.state["sveglie"][0]
        self.assertEqual(sv["data"], "2026-11-10")
        a.ringer.start = lambda: None                      # niente audio nei test
        a.tick(datetime(2026, 11, 10, 5, 39, 59), datetime(2026, 11, 10, 5, 40, 0))
        self.assertEqual(a.suonando["nome"], "Treno")
        self.assertFalse(a.state["sveglie"][0]["attiva"])    # si spegne dopo aver suonato
        self.assertIsNone(a.prossima(datetime(2026, 11, 10, 6, 0))[0])
        a.attiva_sveglia(sid, True)                        # riattivata: va alla prossima volta
        self.assertNotEqual(a.state["sveglie"][0]["data"], "2026-11-10")

    def test_senza_giorni_diventa_una_volta(self):
        a = self.make([{"ora": 6, "minuto": 0, "giorni": []}])
        self.assertIn("data", a.state["sveglie"][0])

    def test_validazione_e_limite(self):
        a = self.make([{"nome": "  ", "ora": 25, "minuto": 61, "giorni": [6, 6, 0, 9]}])
        sv = a.state["sveglie"][0]
        self.assertEqual((sv["nome"], sv["ora"], sv["minuto"], sv["giorni"]), ("Sveglia", 1, 1, [0, 2, 6]))
        for _ in range(9):
            a.salva_sveglia({"ora": 8, "minuto": 0, "giorni": [1]})
        with self.assertRaises(ValueError):
            a.salva_sveglia({"ora": 8, "minuto": 0, "giorni": [1]})

    def test_elimina_e_modifica(self):
        a = self.make([{"nome": "A", "ora": 7, "minuto": 0, "giorni": [0]}, {"nome": "B", "ora": 8, "minuto": 0, "giorni": [0]}])
        a.salva_sveglia({"id": "1", "nome": "A2", "ora": 6, "minuto": 15, "giorni": [0]})
        self.assertEqual(a.state["sveglie"][0]["nome"], "A2")
        a.elimina_sveglia("2")
        self.assertEqual(len(a.state["sveglie"]), 1)
        with self.assertRaises(ValueError):
            a.elimina_sveglia("99")

    def test_migrazione_formato_vecchio(self):
        import json as _json
        p = alarmd.config.state_dir() / "sveglia.json"
        p.write_text(_json.dumps({"attiva": True, "ora": 6, "minuto": 45, "giorni": [0, 1], "snooze_fino": None}))
        a = alarmd.Alarm(dict(alarmd.config.DEFAULT["sveglia"]))
        self.assertEqual(a.state["sveglie"][0]["ora"], 6)
        self.assertNotIn("ora", a.state)
        p.unlink()

    def test_pisolino(self):
        a = self.make()
        a.ringer.start = lambda: None
        a.pisolino(20)
        sn = a.snooze_until()
        a.tick(sn - timedelta(seconds=1), sn)
        self.assertEqual(a.suonando["nome"], "Pisolino")
        with self.assertRaises(ValueError):
            a.pisolino(0)

    def test_pre_sveglia(self):
        a = self.make([{"ora": 7, "minuto": 0, "giorni": [0]}], anticipo_min=15)
        self.assertTrue(a.pre_due(datetime(2026, 11, 16, 6, 44, 59), datetime(2026, 11, 16, 6, 45, 0)))
        self.assertFalse(a.pre_due(datetime(2026, 11, 16, 6, 45, 0), datetime(2026, 11, 16, 6, 45, 1)))

    def test_telefono(self):
        p = alarmd.parse_ha_sveglia
        self.assertEqual(p("07:30:00", "on")["giorni"], list(range(7)))
        sv = p("2026-11-18 06:10:00", None)
        self.assertEqual((sv["data"], sv["ora"], sv["minuto"], sv["attiva"]), ("2026-11-18", 6, 10, True))
        self.assertFalse(p("07:30:00", "off")["attiva"])
        self.assertIsNone(p("unavailable", "on"))
        a = self.make([{"nome": "Lavoro", "ora": 8, "minuto": 0, "giorni": [1]}])
        a.imposta_telefono(p("06:30:00", "on"))
        self.assertEqual(a.prossima(datetime(2026, 11, 17, 0, 0))[1]["nome"], "Dal telefono")
        st = a.status()
        self.assertEqual(st["telefono"]["ora"], 6)
        self.assertEqual(len(st["sveglie"]), 1)                # non viene salvata tra le sveglie

    def test_server(self):
        import json as _json, socket, threading
        a = self.make()
        srv = alarmd.make_server(a, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with socket.create_connection(("127.0.0.1", srv.server_address[1]), timeout=2) as sk:
            f = sk.makefile("rwb")
            for req in ({"cmd": "salva_sveglia", "sveglia": {"nome": "X", "ora": 6, "minuto": 0, "giorni": [1]}},
                        {"cmd": "attiva_sveglia", "id": "1", "attiva": False}):
                f.write((_json.dumps(req) + "\n").encode()); f.flush()
                r = _json.loads(f.readline())
                self.assertTrue(r["ok"], r)
            self.assertFalse(r["stato"]["sveglie"][0]["attiva"])
            f.write(b'{"cmd":"elimina_sveglia","id":"9"}\n'); f.flush()
            self.assertFalse(_json.loads(f.readline())["ok"])
        srv.shutdown()

    def test_chime(self):
        self.make()
        p = alarmd.config.state_dir() / "chime.wav"
        self.assertTrue(p.exists() and p.stat().st_size > 100000)


# ---------------------------------------------------------------- v0.9.1: meteo extra, server
from comodino import allerte as allerte_mod, luna, proxmox  # noqa: E402


class TestLuna(unittest.TestCase):
    def test_fasi_note(self):
        from datetime import timezone
        self.assertEqual(luna.fase(datetime(2024, 1, 25, 17, 54, tzinfo=timezone.utc))["nome"], "Luna piena")
        nuova = luna.fase(datetime(2024, 1, 11, 11, 57, tzinfo=timezone.utc))
        self.assertEqual((nuova["nome"], nuova["icona"]), ("Luna nuova", "🌑"))
        self.assertLessEqual(nuova["illuminazione"], 2)
        self.assertEqual(luna.fase(datetime(2024, 1, 18, 3, 53, tzinfo=timezone.utc))["nome"], "Primo quarto")


class TestPioggiaImminente(unittest.TestCase):
    def m15(self, valori, inizio=datetime(2026, 11, 17, 14, 15)):
        return {"time": [(inizio + timedelta(minutes=15 * i)).isoformat(timespec="minutes") for i in range(len(valori))],
                "precipitation": valori}

    def test_casi(self):
        now = datetime(2026, 11, 17, 14, 20)
        f = weather.pioggia_imminente
        # intervalli che finiscono alle 14:15, 14:30, 14:45...; adesso sono le 14:20 (dentro 14:15-14:30)
        self.assertEqual(f(self.m15([0, 0, 0.4, 1.2, 0, 0]), now), "Pioggia tra ~10 min")     # dalle 14:30
        self.assertEqual(f(self.m15([0, 0, 0, 0, 0.3, 0]), now), "Pioggia tra ~40 min")       # dalle 15:00
        self.assertEqual(f(self.m15([0.9, 0.6, 0.8, 0, 0, 0]), now), "Smette di piovere tra ~25 min")
        self.assertEqual(f(self.m15([0, 0.5] + [0.5] * 6), now), "Piove ora")
        self.assertEqual(f(self.m15([0.7, 0, 0, 0, 0, 0, 0, 0]), now), "")                    # è già finita
        self.assertEqual(f(self.m15([0] * 8), now), "")
        self.assertEqual(f({}, now), "")


def _cap(area, livello, tipo, onset, expires, lang="it-IT", msg="Alert"):
    return {"alert": {"msgType": msg, "info": [
        {"language": "en-GB", "event": "Wind warning", "area": [{"areaDesc": area}], "parameter": []},
        {"language": lang, "event": "Avviso", "headline": "Allerta per vento forte",
         "onset": onset, "expires": expires, "area": [{"areaDesc": area}],
         "parameter": [{"valueName": "awareness_level", "value": f"{livello}; orange; Severe"},
                       {"valueName": "awareness_type", "value": f"{tipo}; Wind"}]}]}}


class TestAllerte(unittest.TestCase):
    def test_parse(self):
        from datetime import timezone
        now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        data = {"warnings": [
            _cap("Sicilia - Palermo", 3, 1, "2026-11-17T06:00:00+01:00", "2026-11-17T23:59:00+01:00"),
            _cap("Sicilia - Palermo", 2, 3, "2026-11-18T06:00:00+01:00", "2026-11-18T20:00:00+01:00"),
            _cap("Sicilia - Palermo", 4, 10, "2026-11-20T06:00:00+01:00", "2026-11-20T20:00:00+01:00"),  # tra 3 giorni
            _cap("Sicilia - Palermo", 2, 4, "2026-11-16T06:00:00+01:00", "2026-11-16T20:00:00+01:00"),   # scaduta
            _cap("Lombardia", 4, 1, "2026-11-17T06:00:00+01:00", "2026-11-17T23:00:00+01:00"),          # altra zona
            _cap("Sicilia - Palermo", 3, 1, "2026-11-17T06:00:00+01:00", "2026-11-17T23:59:00+01:00", msg="Cancel"),
        ]}
        a = allerte_mod.parse(data, "palermo", now)
        self.assertEqual([x["testo"] for x in a], ["Allerta arancione: Vento", "Allerta gialla: Temporali"])
        self.assertTrue(a[0]["in_corso"])
        self.assertFalse(a[1]["in_corso"])
        self.assertEqual(a[0]["dettaglio"], "Allerta per vento forte")       # testo in italiano
        self.assertEqual(allerte_mod.parse(data, "", now), [])
        self.assertEqual(allerte_mod.zone(data), ["Lombardia", "Sicilia - Palermo"])


class TestProxmox(unittest.TestCase):
    RISORSE = [
        {"type": "node", "node": "pve", "status": "online", "cpu": 0.123, "mem": 6 * 1024 ** 3,
         "maxmem": 16 * 1024 ** 3, "uptime": 3 * 86400 + 4 * 3600},
        {"type": "qemu", "vmid": 101, "name": "haos", "status": "running", "cpu": 0.05,
         "mem": 2 * 1024 ** 3, "maxmem": 4 * 1024 ** 3, "uptime": 7200},
        {"type": "lxc", "vmid": 102, "name": "pihole", "status": "stopped", "maxmem": 1024 ** 3},
        {"type": "storage", "storage": "local"},
    ]

    def test_riassunto(self):
        r = proxmox.riassunto(self.RISORSE)
        self.assertEqual((r["attive"], r["totale"]), (1, 2))
        self.assertEqual(r["nodi"][0]["cpu"], 12)
        self.assertEqual(r["nodi"][0]["uptime"], "3g 4h")
        self.assertEqual([(v["tipo"], v["nome"]) for v in r["vm"]], [("VM", "haos"), ("CT", "pihole")])

    def test_nuove_fermate(self):
        prima = proxmox.riassunto(self.RISORSE)["vm"]
        dopo = [dict(v, attiva=False) if v["nome"] == "haos" else v for v in prima]
        self.assertEqual(proxmox.nuove_fermate(prima, dopo), ["haos"])
        self.assertEqual(proxmox.nuove_fermate(prima, prima), [])

    def test_certificato_fissato(self):
        """Server TLS vero con certificato autofirmato: impronta da confermare, poi fissata."""
        import http.server
        import json as _json
        import ssl
        import subprocess
        import threading
        d = tempfile.mkdtemp()
        subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                        "-nodes", "-keyout", f"{d}/k.pem", "-out", f"{d}/c.pem", "-days", "1",
                        "-subj", "/CN=pve"], check=True, capture_output=True)
        visti = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                visti.append(self.headers.get("Authorization"))
                body = _json.dumps({"data": TestProxmox.RISORSE}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(f"{d}/c.pem", f"{d}/k.pem")
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"https://127.0.0.1:{srv.server_address[1]}"
        tid, sec = "comodino@pve!comodino", "segreto"

        with self.assertRaises(proxmox.CertificatoDaConfermare) as cm:
            proxmox.Proxmox(url, tid, sec).stato()
        impronta = cm.exception.impronta
        self.assertEqual(visti, [])                                  # il token non è partito
        self.assertEqual(proxmox.Proxmox(url, tid, sec).impronta_attuale(), impronta)

        r = proxmox.Proxmox(url, tid, sec, impronta).stato()
        self.assertEqual(r["totale"], 2)
        self.assertEqual(visti, [f"PVEAPIToken={tid}={sec}"])

        sbagliata = "AA:" * 31 + "AA"
        with self.assertRaisesRegex(ValueError, "certificato del server è cambiato"):
            proxmox.Proxmox(url, tid, sec, sbagliata).stato()
        self.assertEqual(len(visti), 1)                              # nemmeno qui
        srv.shutdown()


class TestTemperature(unittest.TestCase):
    def test_zone(self):
        from pathlib import Path
        b = Path(tempfile.mkdtemp())
        for i, (tipo, mc) in enumerate((("acpitz", "45000"), ("soc_dts0", "52500"), ("soc_dts1", "51000"), ("rotto", "x"))):
            z = b / f"thermal_zone{i}"
            z.mkdir()
            (z / "type").write_text(tipo + "\n")
            (z / "temp").write_text(mc + "\n")
        self.assertEqual(sistema.temperatura_processore(str(b)), 52.5)
        self.assertIsNone(sistema.temperatura_processore("/inesistente"))
        m = batteria.BatteryManager(full_cfg(), fake_sysfs(cap=50), termico=str(b))
        m.tick()
        self.assertEqual((m.stato["temp_processore"], m.stato["caldo"]), (52.5, False))


class TestWebNuoviCampi(unittest.TestCase):
    def test_proxmox_e_telefono(self):
        cfg = config.load()
        out = webconfig.valida({"px_url": "https://10.0.0.5:8006/", "px_token_id": "comodino@pve!comodino",
                                "px_secret": "x", "ha_sveglia_ora": "input_datetime.sveglia"}, cfg)
        self.assertEqual(out["proxmox"]["url"], "https://10.0.0.5:8006")
        self.assertEqual(out["proxmox"]["fingerprint"], "")            # nuovo indirizzo -> riconferma
        self.assertEqual(out["homeassistant"]["sveglia_ora"], "input_datetime.sveglia")
        cfg["proxmox"]["url"] = "https://10.0.0.5:8006"
        stesso = webconfig.valida({"px_url": "https://10.0.0.5:8006"}, cfg)
        self.assertNotIn("fingerprint", stesso["proxmox"])              # stesso indirizzo: resta fissata
        for bad in ({"px_url": "http://10.0.0.5:8006"}, {"px_token_id": "root"}, {"ha_sveglia_ora": "sveglia"}):
            with self.assertRaises(ValueError):
                webconfig.valida(bad, cfg)


# ---------------------------------------------------------------- v0.9.3: spia del server
class TestSpiaServer(unittest.TestCase):
    def dati(self, **mod):
        r = proxmox.riassunto([
            {"type": "node", "node": "pve", "status": "online", "cpu": 0.2, "mem": 4, "maxmem": 16},
            {"type": "qemu", "vmid": 100, "name": "haos", "status": "running"},
            {"type": "lxc", "vmid": 101, "name": "pihole", "status": "running"},
            {"type": "qemu", "vmid": 102, "name": "test", "status": "stopped"},
            {"type": "qemu", "vmid": 9000, "name": "debian-tpl", "status": "stopped", "template": 1},
        ])
        r.update(configurato=True, ok=True, **mod)
        return r

    def test_livelli(self):
        sp = proxmox.spia
        self.assertIsNone(sp({"configurato": False}))
        self.assertEqual(sp(self.dati())["testo"], "1 macchina ferma: test")
        ok = sp(self.dati(), ignora=[102])                       # spenta apposta
        self.assertEqual(ok, {"livello": "ok", "testo": "Server ok · 2/2 attive"})   # template esclusi
        d = self.dati()
        d["nodi"][0]["cpu"] = 95
        self.assertEqual(sp(d, [102])["livello"], "attenzione")
        d["nodi"][0]["attivo"] = False
        self.assertEqual(sp(d, [102]), {"livello": "errore", "testo": "Nodo offline: pve"})
        self.assertEqual(sp({"configurato": True, "ok": False, "errore": "x"})["testo"], "Server non raggiungibile")
        self.assertEqual(sp({"configurato": True, "ok": False, "impronta_nuova": "AA"})["livello"], "attenzione")
        self.assertEqual(self.dati()["nodi"][0]["ram_pct"], 25)


# ---------------------------------------------------------------- v0.9.4: termometro misurato
from datetime import timezone  # noqa: E402
class TestClimaMisurato(unittest.TestCase):
    def setUp(self):
        from comodino import homeassistant
        self.ha = homeassistant
        self.c = {"interno_temp": "", "interno_umidita": "",
                  "esterno_temp": "sensor.xiron_0801_temp", "esterno_umidita": "sensor.xiron_0801_hum",
                  "esterno_batteria": ""}
        self.ora = datetime(2026, 11, 20, 2, 0, tzinfo=timezone.utc)

    def _s(self, eid, stato, minuti_fa=1):
        t = (self.ora - timedelta(minutes=minuti_fa)).isoformat()
        return {"id": eid, "stato": stato, "aggiornato": t}

    def test_pila_ricavata_da_rflink(self):
        self.assertEqual(self.ha.entita_clima(self.c)["esterno_batteria"], "sensor.xiron_0801_bat")
        c = dict(self.c, esterno_batteria="sensor.altra_pila")
        self.assertEqual(self.ha.entita_clima(c)["esterno_batteria"], "sensor.altra_pila")
        c = dict(self.c, esterno_temp="sensor.balcone")
        self.assertNotIn("esterno_batteria", self.ha.entita_clima(c))

    def test_misura_e_pila(self):
        out = self.ha.clima_da_stati(self.c, [
            self._s("sensor.xiron_0801_temp", "22.34"), self._s("sensor.xiron_0801_hum", "34"),
            self._s("sensor.xiron_0801_bat", "low")], self.ora)
        self.assertEqual(out, {"esterno": {"temp": 22.3, "umidita": 34, "pila_scarica": True}})
        out = self.ha.clima_da_stati(self.c, [
            self._s("sensor.xiron_0801_temp", "-1.0"), self._s("sensor.xiron_0801_bat", "ok")], self.ora)
        self.assertEqual(out, {"esterno": {"temp": -1.0}})

    def test_sensore_muto(self):
        out = self.ha.clima_da_stati(self.c, [self._s("sensor.xiron_0801_temp", "22", minuti_fa=180)], self.ora)
        self.assertEqual(out, {"esterno": {"vecchio": True}})
        out = self.ha.clima_da_stati(self.c, [self._s("sensor.xiron_0801_temp", "unavailable")], self.ora)
        self.assertEqual(out, {})

    def test_pila_numerica(self):
        self.assertTrue(self.ha.pila_scarica("10"))
        self.assertFalse(self.ha.pila_scarica("80"))
        self.assertFalse(self.ha.pila_scarica("unknown"))

    def test_web_pila(self):
        out = webconfig.valida({"clima": {"esterno_batteria": "sensor.xiron_0801_bat"}})
        self.assertEqual(out["clima"]["esterno_batteria"], "sensor.xiron_0801_bat")


# ---------------------------------------------------------------- v0.9.5: muffa, terremoti, storico
class TestMuffa(unittest.TestCase):
    def test_rugiada(self):
        from comodino import muffa
        self.assertAlmostEqual(muffa.punto_rugiada(20, 50), 9.3, delta=0.2)
        self.assertAlmostEqual(muffa.umidita_assoluta(20, 50), 8.6, delta=0.2)

    def test_livelli(self):
        from comodino import muffa
        self.assertIsNone(muffa.rischio(None, 50, 10))
        self.assertEqual(muffa.rischio(21, 45, 12)["livello"], "ok")
        self.assertEqual(muffa.rischio(20, 65, 5)["livello"], "rischio")
        r = muffa.rischio(18, 80, 2, fattore=0.55)
        self.assertEqual(r["livello"], "condensa")
        self.assertEqual(r["ur_muro"], 100)
        # d'estate, fuori più caldo: il muro non è più freddo della stanza
        self.assertEqual(muffa.rischio(26, 60, 32)["livello"], "ok")


class TestTerremoti(unittest.TestCase):
    TESTO = (
        "#EventID|Time|Latitude|Longitude|Depth/Km|Author|Catalog|Contributor|ContributorID|"
        "MagType|Magnitude|MagAuthor|EventLocationName|EventType\n"
        "111|2026-11-20T18:00:00.120000|38.40|14.90|10.2|SURVEY-INGV||||ML|3.1|--|Isole Eolie (Messina)|earthquake\n"
        "222|2026-11-20T19:30:00|37.90|14.00|8.0|SURVEY-INGV||||ML|3.8|--|2 km N Collesano (PA)|earthquake\n"
        "rotta|x|y\n")

    def test_parse_e_avviso(self):
        from comodino import terremoti
        ora = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
        ev = terremoti.parse(self.TESTO, 38.0, 13.95, ora)
        self.assertEqual([e["id"] for e in ev], ["222", "111"])       # dal più recente
        self.assertTrue(ev[0]["forte"])                               # 3.8 a ~12 km
        self.assertFalse(ev[1]["forte"])
        self.assertEqual(ev[0]["ore_fa"], 0.5)
        av = terremoti.avviso(ev)
        self.assertIn("M3.8", av["testo"])
        self.assertEqual(av["colore"], "#f85149")
        self.assertIsNone(terremoti.avviso([]))
        self.assertEqual(terremoti.parse("", 38, 14), [])

    def test_distanza(self):
        from comodino import terremoti
        self.assertAlmostEqual(terremoti.distanza_km(38.0, 13.0, 38.0, 14.0), 87.6, delta=1)


class TestStorico(unittest.TestCase):
    def test_punti(self):
        from comodino.storico import Storico
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            s = Storico(path)
            t0 = int(__import__("time").time()) - 26 * 3600
            self.assertTrue(s.aggiungi(20.1, None, t0))
            self.assertFalse(s.aggiungi(20.2, None, t0 + 60))          # troppo presto
            self.assertFalse(s.aggiungi(None, None, t0 + 700))         # niente da salvare
            self.assertTrue(s.aggiungi(20.3, 21.0, t0 + 600))
            self.assertTrue(s.aggiungi(19.0, 21.0, t0 + 25 * 3600))    # i vecchi vanno via
            self.assertEqual(len(s.punti), 1)
            s2 = Storico(path)
            s2._pota(t0 + 25 * 3600)
            self.assertEqual(s2.punti, [{"t": t0 + 25 * 3600, "f": 19.0, "d": 21.0}])


class TestWebNuovi(unittest.TestCase):
    def test_terremoti(self):
        out = webconfig.valida({"terremoti": {"attivi": True, "raggio_km": "80", "magnitudo_min": "2.5", "ore": 6}})
        self.assertEqual(out["terremoti"], {"attivi": True, "raggio_km": 80, "magnitudo_min": 2.5, "ore": 6})
        with self.assertRaises(ValueError):
            webconfig.valida({"terremoti": {"raggio_km": 5000, "magnitudo_min": 3}})

    def test_fattore_muro(self):
        out = webconfig.valida({"clima": {"fattore_muro": 0.55}})
        self.assertEqual(out["clima"]["fattore_muro"], 0.55)
        with self.assertRaises(ValueError):
            webconfig.valida({"clima": {"fattore_muro": 2}})
