import QtQuick
import QtQuick.Layouts

// Selettore di orario a passi di 30 minuti: [ − ] 22:30 [ + ]
RowLayout {
    id: o
    property var tema
    property real u: 1
    property string valore: "00:00"
    signal cambiato(string v)
    spacing: 14 * u

    function sposta(delta) {
        var p = valore.split(":")
        var m = (parseInt(p[0]) * 60 + parseInt(p[1]) + delta + 1440) % 1440
        var h = Math.floor(m / 60), mm = m % 60
        cambiato((h < 10 ? "0" : "") + h + ":" + (mm < 10 ? "0" : "") + mm)
    }

    BigButton { tema: o.tema; u: o.u; text: "−"; implicitWidth: 100 * o.u; onClicked: o.sposta(-30) }
    Text {
        text: o.valore
        color: o.tema.testo
        font.pixelSize: 48 * o.u
        horizontalAlignment: Text.AlignHCenter
        Layout.preferredWidth: 160 * o.u
    }
    BigButton { tema: o.tema; u: o.u; text: "+"; implicitWidth: 100 * o.u; onClicked: o.sposta(30) }
}
