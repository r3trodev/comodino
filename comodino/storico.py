"""Temperature delle ultime 24 ore, un punto ogni 10 minuti, salvate sul tablet."""
import json
import os
import time


class Storico:
    def __init__(self, path, ore=24, passo=600):
        self.path, self.ore, self.passo = path, ore, passo
        self.punti = []
        try:
            with open(path) as f:
                self.punti = [p for p in json.load(f) if isinstance(p, dict) and "t" in p]
        except (OSError, ValueError):
            pass
        self._pota(time.time())

    def _pota(self, adesso):
        limite = adesso - self.ore * 3600
        self.punti = [p for p in self.punti if limite <= p["t"] <= adesso + 60]

    def aggiungi(self, fuori, dentro, adesso=None):
        """True se ha registrato un nuovo punto."""
        adesso = adesso if adesso is not None else time.time()
        if fuori is None and dentro is None:
            return False
        if self.punti and adesso - self.punti[-1]["t"] < self.passo - 30:
            return False
        self.punti.append({"t": round(adesso), "f": fuori, "d": dentro})
        self._pota(adesso)
        self._salva()
        return True

    def _salva(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(self.punti, f)
            os.replace(tmp, self.path)
        except OSError:
            pass
