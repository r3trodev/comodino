"""Spegnimento vero del display (DPMS) tramite il compositor.

Su alcuni tablet (es. Chuwi Hi10 Pro, pannello DSI Intel) la retroilluminazione a 0 lascia
comunque un bagliore e bl_power viene ignorato: l'unico modo di spegnere tutto è chiedere
al compositor di mettere l'uscita in "off". labwc lo permette con il protocollo
wlr-output-power-management (comando wlopm); cage no. Se non è disponibile si ripiega sulla
retroilluminazione a 0.

Il touch continua ad arrivare all'app anche a display spento (verificato su labwc).
"""
import shutil
import subprocess


class Display:
    def __init__(self, comando="wlopm", esegui=None):
        self.comando = shutil.which(comando) if esegui is None else comando
        self._esegui = esegui or self._subprocess
        self.supportato = None       # None = non ancora verificato
        self.acceso = True
        self.errore = ""

    @staticmethod
    def _subprocess(args):
        r = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return r.returncode, (r.stdout + r.stderr).strip()

    def _verifica(self):
        if self.supportato is not None:
            return self.supportato
        if not self.comando:
            self.supportato, self.errore = False, "wlopm non installato"
            return False
        try:
            codice, uscita = self._esegui([self.comando])
        except (OSError, subprocess.SubprocessError) as e:
            codice, uscita = 1, str(e)
        self.supportato = codice == 0 and "not support" not in uscita.lower()
        self.errore = "" if self.supportato else (uscita[:160] or "non supportato dal compositor")
        return self.supportato

    def _imposta(self, on):
        if not self._verifica():
            return False
        try:
            codice, uscita = self._esegui([self.comando, "--on" if on else "--off", "*"])
        except (OSError, subprocess.SubprocessError) as e:
            codice, uscita = 1, str(e)
        if codice != 0:
            self.errore = uscita[:160]
            return False
        self.acceso, self.errore = on, ""
        return True

    def spegni(self):
        """True se il display è stato spento davvero (altrimenti usa la retroilluminazione)."""
        return True if not self.acceso else self._imposta(False)

    def accendi(self, forza=False):
        if self.acceso and not forza:
            return True
        return self._imposta(True)

    def stato(self):
        return {"supportato": bool(self._verifica()), "acceso": self.acceso, "errore": self.errore}
