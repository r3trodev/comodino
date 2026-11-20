import QtQuick

// Icona meteo in un riquadro di dimensione fissa, con un cerchio chiaro dietro:
// tutte le icone occupano lo stesso spazio (niente righe storte) e quelle scure,
// come la nuvola, restano leggibili anche sui temi scuri.
Item {
    id: ic
    property string testo: ""
    property real dim: 64
    property var tema
    implicitWidth: dim
    implicitHeight: dim
    width: dim
    height: dim

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: ic.tema.testo
        opacity: 0.12
    }
    Text {
        anchors.centerIn: parent
        text: ic.testo
        // font a colori esplicito: altrimenti ☁ ☀ ⛅ ❄ ⛈ escono in bianco e nero da DejaVu
        font.family: "Noto Color Emoji"
        font.pixelSize: ic.dim * 0.6
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
