import QtQuick

Text {
    property var tema
    property real u: 1
    color: tema.testo
    font.pixelSize: 42 * u
    font.weight: Font.Bold
}
