import QtQuick

// Temperature delle ultime 24 ore: fuori (colore d'accento) e dentro (colore del testo).
// punti: [{t: secondi epoch, f: fuori o null, d: dentro o null}, ...]
Item {
    id: g
    property var tema
    property real u: 1
    property var punti: []

    readonly property bool haDentro: {
        for (var i = 0; i < punti.length; i++) if (punti[i].d !== null && punti[i].d !== undefined) return true
        return false
    }
    readonly property bool pochi: punti.length < 3

    onPuntiChanged: tela.requestPaint()
    onTemaChanged: tela.requestPaint()

    Row {   // legenda
        id: legenda
        anchors.top: parent.top
        anchors.left: parent.left
        spacing: 22 * g.u
        Text { text: "Ultime 24 ore"; color: g.tema.tenue; font.family: "DejaVu Sans Mono"; font.pixelSize: 22 * g.u }
        Text { text: "━ fuori"; color: g.tema.accento; font.family: "DejaVu Sans Mono"; font.pixelSize: 22 * g.u }
        Text { visible: g.haDentro; text: "━ dentro"; color: g.tema.testo; font.family: "DejaVu Sans Mono"; font.pixelSize: 22 * g.u }
    }

    Text {
        anchors.centerIn: tela
        visible: g.pochi
        text: "Il grafico si riempie nelle prossime ore"
        color: g.tema.tenue
        font.family: "DejaVu Sans Mono"
        font.pixelSize: 22 * g.u
    }

    Canvas {
        id: tela
        anchors.top: legenda.bottom
        anchors.topMargin: 6 * g.u
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 12 * g.u
        visible: !g.pochi
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var p = g.punti
            if (p.length < 3 || width <= 0 || height <= 0) return

            var adesso = Date.now() / 1000
            var inizio = adesso - 24 * 3600
            var lo = 1e9, hi = -1e9
            for (var i = 0; i < p.length; i++) {
                var vals = [p[i].f, p[i].d]
                for (var k = 0; k < 2; k++) {
                    var v = vals[k]
                    if (v === null || v === undefined) continue
                    if (v < lo) lo = v
                    if (v > hi) hi = v
                }
            }
            if (lo > hi) return
            lo = Math.floor(lo - 0.5); hi = Math.ceil(hi + 0.5)
            if (hi - lo < 4) { var c = (hi + lo) / 2; lo = Math.floor(c - 2); hi = Math.ceil(c + 2) }

            var fs = Math.round(20 * g.u)
            var sx = 58 * g.u                 // spazio per le etichette dei gradi
            var basso = height - fs - 8 * g.u // spazio per le ore
            var w = width - sx
            function X(t) { return sx + (t - inizio) / (24 * 3600) * w }
            function Y(v) { return basso - (v - lo) / (hi - lo) * (basso - 4 * g.u) }

            // griglia e etichette
            ctx.font = fs + "px 'DejaVu Sans Mono'"
            ctx.fillStyle = g.tema.tenue
            ctx.strokeStyle = g.tema.tenue
            ctx.globalAlpha = 0.25
            ctx.lineWidth = 1
            var passi = [lo, Math.round((lo + hi) / 2), hi]
            for (var j = 0; j < passi.length; j++) {
                ctx.beginPath(); ctx.moveTo(sx, Y(passi[j])); ctx.lineTo(width, Y(passi[j])); ctx.stroke()
            }
            for (var h = 0; h <= 24; h += 6) {
                ctx.beginPath(); ctx.moveTo(X(inizio + h * 3600), 0); ctx.lineTo(X(inizio + h * 3600), basso); ctx.stroke()
            }
            ctx.globalAlpha = 1
            ctx.textBaseline = "middle"
            for (j = 0; j < passi.length; j++) ctx.fillText(passi[j] + "°", 0, Y(passi[j]))
            ctx.textBaseline = "alphabetic"
            for (h = 0; h <= 24; h += 6) {
                var d = new Date((inizio + h * 3600) * 1000)
                var et = h === 24 ? "ora" : Qt.formatTime(d, "HH:mm")
                var tw = ctx.measureText(et).width
                var x = Math.min(Math.max(X(inizio + h * 3600) - tw / 2, sx), width - tw)
                ctx.fillText(et, x, height - 2 * g.u)
            }

            // linee: si interrompono se manca un dato o c'è un buco di più di 40 minuti
            function linea(chiave, colore) {
                ctx.strokeStyle = colore
                ctx.lineWidth = 3 * g.u
                ctx.lineJoin = "round"
                ctx.beginPath()
                var aperta = false, tPrima = 0
                for (var i = 0; i < p.length; i++) {
                    var v = p[i][chiave]
                    if (v === null || v === undefined || p[i].t < inizio) { aperta = false; continue }
                    if (aperta && p[i].t - tPrima <= 40 * 60) ctx.lineTo(X(p[i].t), Y(v))
                    else ctx.moveTo(X(p[i].t), Y(v))
                    aperta = true; tPrima = p[i].t
                }
                ctx.stroke()
            }
            linea("f", g.tema.accento)
            if (g.haDentro) linea("d", g.tema.testo)
        }
    }

    // ogni 10 minuti l'asse del tempo scorre anche se non arrivano punti nuovi
    Timer { interval: 10 * 60 * 1000; running: true; repeat: true; onTriggered: tela.requestPaint() }
}
