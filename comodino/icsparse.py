"""Parser iCalendar minimale per il link iCal privato di Google Calendar.

Gestisce: eventi singoli e di tutto il giorno, TZID, orari UTC, RRULE,
EXDATE, istanze modificate (RECURRENCE-ID) ed eventi annullati.
Dipendenze: solo python3-dateutil.
"""
import re
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

UTC = timezone.utc
GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def fetch(url, timeout=20):
    # Google a volte fornisce il link come webcal://
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "comodino/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------- parsing

def _unfold(text):
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def _split_line(line):
    """'DTSTART;TZID=Europe/Rome:2026...' -> ('DTSTART', {'TZID': ...}, '2026...')"""
    in_q = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_q = not in_q
        elif ch == ":" and not in_q:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return None
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


def _parse_dt(value, params, deftz):
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    if value.endswith("Z"):
        return datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    naive = datetime.strptime(value, "%Y%m%dT%H%M%S")
    tz = deftz
    if "TZID" in params:
        try:
            tz = ZoneInfo(params["TZID"])
        except Exception:
            pass
    return naive.replace(tzinfo=tz)


_DUR = re.compile(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


def _parse_duration(v):
    m = _DUR.fullmatch(v.strip())
    if not m:
        return None
    sign, w, d, h, mi, s = m.groups()
    td = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0),
                   minutes=int(mi or 0), seconds=int(s or 0))
    return -td if sign == "-" else td


def parse(text, deftz):
    """Restituisce una lista di dict evento 'grezzi'."""
    events, cur, skip_depth = [], None, 0
    for line in _unfold(text):
        sp = _split_line(line)
        if not sp:
            continue
        name, params, value = sp
        if name == "BEGIN":
            if value.upper() == "VEVENT":
                cur = {"exdate": set()}
            elif cur is not None:
                skip_depth += 1          # es. VALARM dentro VEVENT
            continue
        if name == "END":
            if value.upper() == "VEVENT" and cur is not None:
                if "dtstart" in cur:
                    events.append(cur)
                cur, skip_depth = None, 0
            elif skip_depth:
                skip_depth -= 1
            continue
        if cur is None or skip_depth:
            continue
        try:
            if name == "DTSTART":
                cur["dtstart"] = _parse_dt(value, params, deftz)
            elif name == "DTEND":
                cur["dtend"] = _parse_dt(value, params, deftz)
            elif name == "DURATION":
                cur["duration"] = _parse_duration(value)
            elif name == "SUMMARY":
                cur["summary"] = _unescape(value)
            elif name == "LOCATION":
                cur["location"] = _unescape(value)
            elif name == "UID":
                cur["uid"] = value
            elif name == "RRULE":
                cur["rrule"] = value
            elif name == "EXDATE":
                for v in value.split(","):
                    cur["exdate"].add(_key(_parse_dt(v, params, deftz)))
            elif name == "RECURRENCE-ID":
                cur["recurrence_id"] = _key(_parse_dt(value, params, deftz))
            elif name == "STATUS":
                cur["status"] = value.upper()
        except ValueError:
            continue
    return events


# ---------------------------------------------------------------- espansione

def _key(d):
    if isinstance(d, datetime):
        return d.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return d.strftime("%Y%m%d")


def _is_allday(d):
    return isinstance(d, date) and not isinstance(d, datetime)


def _as_dt(d, tz):
    if _is_allday(d):
        return datetime.combine(d, time(0), tz)
    return d


def _duration(ev):
    s = ev["dtstart"]
    if "dtend" in ev and type(ev["dtend"]) is type(s):
        return ev["dtend"] - s
    if ev.get("duration") is not None:
        return ev["duration"]
    return timedelta(days=1) if _is_allday(s) else timedelta(0)


def _fix_until(rule, aware):
    """dateutil vuole UNTIL in UTC se DTSTART ha un fuso: normalizza."""
    if not aware:
        return re.sub(r"UNTIL=(\d{8})(T\d{6})?Z", lambda m: "UNTIL=" + m.group(1) + (m.group(2) or ""), rule)

    def repl(m):
        val = m.group(1)
        if val.endswith("Z"):
            return m.group(0)
        if len(val) == 8:
            return f"UNTIL={val}T235959Z"
        return f"UNTIL={val}Z"
    return re.sub(r"UNTIL=([0-9TZ]+)", repl, rule)


def occurrences(events, start, end, tz):
    """Istanze degli eventi che si sovrappongono a [start, end)."""
    overrides = {}
    masters = []
    for ev in events:
        if "recurrence_id" in ev and "uid" in ev:
            overrides[(ev["uid"], ev["recurrence_id"])] = ev
        else:
            masters.append(ev)

    out = []

    def emit(ev, s):
        if ev.get("status") == "CANCELLED":
            return
        dur = _duration(ev)
        e = s + dur
        s_dt, e_dt = _as_dt(s, tz), _as_dt(e, tz)
        if e_dt == s_dt:
            e_dt = s_dt + timedelta(seconds=1)
        if e_dt > start and s_dt < end:
            out.append({
                "titolo": ev.get("summary", "(senza titolo)"),
                "luogo": ev.get("location", ""),
                "inizio": s_dt,
                "fine": e_dt,
                "tutto_il_giorno": _is_allday(s),
            })

    for ev in masters:
        s0 = ev["dtstart"]
        if "rrule" not in ev:
            emit(ev, s0)
            continue
        dur = _duration(ev)
        allday = _is_allday(s0)
        try:
            if allday:
                rule = rrulestr(_fix_until(ev["rrule"], False),
                                dtstart=datetime.combine(s0, time(0)))
                lo = (start - dur).astimezone(tz).replace(tzinfo=None) - timedelta(days=1)
                hi = end.astimezone(tz).replace(tzinfo=None)
                occs = [o.date() for o in rule.between(lo, hi, inc=True)]
            else:
                rule = rrulestr(_fix_until(ev["rrule"], True), dtstart=s0)
                occs = rule.between(start - dur - timedelta(seconds=1), end, inc=True)
        except (ValueError, TypeError):
            emit(ev, s0)
            continue
        uid = ev.get("uid")
        for o in occs:
            if not allday and o.tzinfo is None:
                o = o.replace(tzinfo=s0.tzinfo)
            k = _key(o)
            if k in ev["exdate"] or (uid, k) in overrides:
                continue
            emit(ev, o)

    for ev in overrides.values():
        emit(ev, ev["dtstart"])

    out.sort(key=lambda x: (x["inizio"], not x["tutto_il_giorno"], x["titolo"]))
    return out


# ---------------------------------------------------------------- agenda per la UI

def _day_label(d, today):
    if d == today:
        return "Oggi"
    if d == today + timedelta(days=1):
        return "Domani"
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def agenda(items, now, tz):
    today = now.astimezone(tz).date()
    rows = []
    for it in items:
        s = it["inizio"].astimezone(tz)
        e = it["fine"].astimezone(tz)
        # eventi a cavallo di più giorni: mostrali dal giorno corrente
        show_day = max(s.date(), today)
        rows.append({
            "giorno": _day_label(show_day, today),
            "ordine": show_day.isoformat(),
            "ora": "Tutto il giorno" if it["tutto_il_giorno"] else s.strftime("%H:%M"),
            "titolo": it["titolo"],
            "luogo": it["luogo"],
            "passato": e <= now,
        })
    rows.sort(key=lambda r: (r["ordine"], r["ora"] != "Tutto il giorno", r["ora"]))
    return rows


def spiega_errore(e):
    """Traduce un errore di rete/parsing in una frase breve e utile."""
    import ssl
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (401, 403, 404):
            return f"link non valido o revocato (HTTP {e.code})"
        return f"errore del server (HTTP {e.code})"
    reason = getattr(e, "reason", e)
    if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
        return "certificato non valido: l'ora del tablet è sincronizzata?"
    if isinstance(e, urllib.error.URLError):
        txt = str(reason)
        if "Name or service not known" in txt or "Temporary failure in name resolution" in txt:
            return "rete non disponibile (DNS)"
        return f"rete non disponibile ({txt[:60]})"
    if isinstance(e, TimeoutError) or "timed out" in str(e):
        return "tempo scaduto"
    if isinstance(e, (ValueError, KeyError)):
        return f"file del calendario non leggibile ({str(e)[:60]})"
    return str(e)[:80]


def load_agenda(urls, tz_name="Europe/Rome", days=7, now=None):
    tz = ZoneInfo(tz_name)
    now = now or datetime.now(tz)
    start = datetime.combine(now.astimezone(tz).date(), time(0), tz)
    end = start + timedelta(days=days)
    items, errors = [], []
    for url in urls:
        try:
            items += occurrences(parse(fetch(url), tz), start, end, tz)
        except Exception as e:  # rete assente, URL errato...
            errors.append(spiega_errore(e))
    return agenda(items, now, tz), errors
