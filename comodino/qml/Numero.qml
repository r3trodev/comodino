import QtQuick
import QtQuick.Layouts

// Selettore numerico: [ − ] 40% [ + ]
RowLayout {
    id: n
    property var tema
    property real u: 1
    property int valore: 0
    property int minimo: 0
    property int massimo: 100
    property int passo: 5
    property string suffisso: "%"
    signal cambiato(int v)
    spacing: 14 * u

    BigButton {
        tema: n.tema; u: n.u; text: "−"; implicitWidth: 100 * n.u
        opacity: n.valore > n.minimo ? 1 : 0.35
        onClicked: if (n.valore > n.minimo) n.cambiato(Math.max(n.minimo, n.valore - n.passo))
    }
    Text {
        text: n.valore + n.suffisso
        color: n.tema.testo
        font.pixelSize: 46 * n.u
        horizontalAlignment: Text.AlignHCenter
        Layout.preferredWidth: 150 * n.u
    }
    BigButton {
        tema: n.tema; u: n.u; text: "+"; implicitWidth: 100 * n.u
        opacity: n.valore < n.massimo ? 1 : 0.35
        onClicked: if (n.valore < n.massimo) n.cambiato(Math.min(n.massimo, n.valore + n.passo))
    }
}
