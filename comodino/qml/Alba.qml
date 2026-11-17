import QtQuick

// Alba simulata: nei minuti prima della sveglia lo schermo passa piano dal nero
// al rosso, all'arancio, al bianco caldo (la luminosità la alza il backend).
// Un tocco la nasconde fino alla sveglia.
Rectangle {
    id: alba
    property real u: 1
    property date adesso: new Date()
    readonly property real p: Math.max(0, backend.alba)

    function mix(a, b, t) {
        return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1)
    }
    readonly property color c0: "#000000"
    readonly property color c1: "#5a1300"
    readonly property color c2: "#d9661f"
    readonly property color c3: "#fff0d6"

    visible: backend.alba >= 0
    color: p < 0.33 ? mix(c0, c1, p / 0.33)
         : p < 0.66 ? mix(c1, c2, (p - 0.33) / 0.33)
                    : mix(c2, c3, (p - 0.66) / 0.34)
    Behavior on color { ColorAnimation { duration: 4000 } }

    Column {
        anchors.centerIn: parent
        spacing: 20 * alba.u
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatTime(alba.adesso, "HH:mm")
            font.pixelSize: 260 * alba.u
            font.weight: Font.Light
            color: alba.p < 0.6 ? Qt.rgba(1, 0.75, 0.55, 0.35 + alba.p) : "#5a2a10"
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "🌅  Sveglia alle " + (backend.sveglia.prossima ? backend.sveglia.prossima.substr(11, 5) : "")
            font.pixelSize: 40 * alba.u
            color: alba.p < 0.6 ? Qt.rgba(1, 0.75, 0.55, 0.3 + alba.p) : "#7a3a18"
        }
    }
    MouseArea { anchors.fill: parent; onClicked: backend.albaNascondi() }
}
