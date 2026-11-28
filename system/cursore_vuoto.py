#!/usr/bin/env python3
"""Crea un tema di cursori trasparente: sul Comodino si usa solo il touch e la freccia del
mouse non deve mai comparire. Uso: cursore_vuoto.py <cartella icone> (crea <cartella>/comodino-vuoto)."""
import os
import struct
import sys

NOMI = ["default", "left_ptr", "arrow", "top_left_arrow", "pointer", "hand1", "hand2", "text",
        "xterm", "ibeam", "wait", "watch", "progress", "left_ptr_watch", "crosshair", "move",
        "grab", "grabbing", "all-scroll", "not-allowed", "col-resize", "row-resize", "n-resize",
        "s-resize", "e-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize",
        "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "help", "context-menu"]


def xcursor_trasparente(lato=24):
    """File Xcursor con una sola immagine lato x lato completamente trasparente."""
    tipo_img, header_img = 0xFFFD0002, 36
    pixel = b"\0\0\0\0" * (lato * lato)
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, 1)
    toc = struct.pack("<III", tipo_img, lato, 16 + 12)
    img = struct.pack("<IIIIIIIII", header_img, tipo_img, lato, 1, lato, lato, 0, 0, 0)
    return header + toc + img + pixel


def crea(base):
    tema = os.path.join(base, "comodino-vuoto")
    cartella = os.path.join(tema, "cursors")
    os.makedirs(cartella, exist_ok=True)
    with open(os.path.join(tema, "index.theme"), "w") as f:
        f.write("[Icon Theme]\nName=comodino-vuoto\nComment=Cursore invisibile\n")
    dati = xcursor_trasparente()
    for nome in NOMI:
        with open(os.path.join(cartella, nome), "wb") as f:
            f.write(dati)
    return tema


if __name__ == "__main__":
    crea(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.local/share/icons"))
