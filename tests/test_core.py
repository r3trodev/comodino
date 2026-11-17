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


class TestAlarm(unittest.TestCase):
    def make(self, **state):
        cfg = dict(alarmd.config.DEFAULT["sveglia"])
        a = alarmd.Alarm(cfg)
        a.state = dict(alarmd.DEFAULT_STATE, **state)
        return a

    def test_next_weekday(self):
        a = self.make(attiva=True, ora=7, minuto=0, giorni=[0, 1, 2, 3, 4])
        fri_evening = datetime(2026, 11, 20, 22, 0)        # venerdì
        self.assertEqual(a.next_after(fri_evening), datetime(2026, 11, 23, 7, 0))   # lunedì
        self.assertEqual(a.next_after(datetime(2026, 11, 16, 6, 59)), datetime(2026, 11, 16, 7, 0))
        self.assertEqual(a.next_after(datetime(2026, 11, 16, 7, 0)), datetime(2026, 11, 17, 7, 0))

    def test_inactive_and_snooze(self):
        a = self.make(attiva=False)
        self.assertIsNone(a.next_after(datetime(2026, 11, 16, 6, 0)))
        a.state["snooze_fino"] = "2026-11-16T07:09:00"
        self.assertEqual(a.next_after(datetime(2026, 11, 16, 7, 1)), datetime(2026, 11, 16, 7, 9))

    def test_configure_sanitizes(self):
        a = self.make()
        a.configure({"attiva": True, "ora": 25, "minuto": 61, "giorni": [6, 6, 0, 9]})
        self.assertEqual((a.state["ora"], a.state["minuto"], a.state["giorni"]), (1, 1, [0, 2, 6]))

    def test_chime(self):
        self.make()
        p = alarmd.config.state_dir() / "chime.wav"
        self.assertTrue(p.exists() and p.stat().st_size > 100000)

    def test_server_roundtrip(self):
        import json, socket, threading
        a = self.make()
        srv = alarmd.make_server(a, 0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
            f = s.makefile("rwb")
            f.write(b'{"cmd":"imposta","attiva":true,"ora":6,"minuto":45,"giorni":[5]}\n'); f.flush()
            r = json.loads(f.readline())
            self.assertTrue(r["ok"])
            self.assertEqual(r["stato"]["ora"], 6)
            self.assertFalse(r["stato"]["suona"])
            f.write(b'{"cmd":"boh"}\n'); f.flush()
            self.assertFalse(json.loads(f.readline())["ok"])
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()


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


class TestPreAlarm(unittest.TestCase):
    def test_pre_due(self):
        cfg = dict(alarmd.config.DEFAULT["sveglia"])
        a = alarmd.Alarm(cfg, {"url": "", "token": "", "anticipo_min": 15})
        a.state = dict(alarmd.DEFAULT_STATE, attiva=True, ora=7, minuto=0, giorni=[0])
        self.assertTrue(a.pre_due(datetime(2026, 11, 16, 6, 44, 59), datetime(2026, 11, 16, 6, 45, 0)))
        self.assertFalse(a.pre_due(datetime(2026, 11, 16, 6, 45, 0), datetime(2026, 11, 16, 6, 45, 1)))
        self.assertFalse(a.pre_due(datetime(2026, 11, 16, 6, 30), datetime(2026, 11, 16, 6, 31)))
        a.anticipo = 0
        self.assertFalse(a.pre_due(datetime(2026, 11, 16, 6, 44, 59), datetime(2026, 11, 16, 6, 45, 0)))


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
