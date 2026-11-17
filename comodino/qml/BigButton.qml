import QtQuick

// Pulsante grande e semplice, pensato per il touch.
Rectangle {
    id: b
    property alias text: label.text
    property bool primary: false
    property var tema
    property real u: 1
    property real fontSize: 34 * u
    signal clicked()

    radius: 20 * u
    implicitWidth: label.implicitWidth + 64 * u
    implicitHeight: 100 * u
    color: primary ? tema.accento : "transparent"
    border.color: primary ? tema.accento : tema.tenue
    border.width: 2
    opacity: area.pressed ? 0.65 : 1.0

    Text {
        id: label
        anchors.centerIn: parent
        color: b.primary ? b.tema.sfondo : b.tema.testo
        font.pixelSize: b.fontSize
        font.weight: Font.DemiBold
    }
    MouseArea {
        id: area
        anchors.fill: parent
        onClicked: b.clicked()
    }
}
