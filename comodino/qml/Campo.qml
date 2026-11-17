import QtQuick
import QtQuick.Controls

// Campo di testo grande, in tema scuro, per il touch.
TextField {
    id: f
    property var tema
    property real u: 1
    font.pixelSize: 36 * u
    color: tema.testo
    placeholderTextColor: tema.tenue
    leftPadding: 22 * u
    rightPadding: 22 * u
    implicitHeight: 96 * u
    inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
    background: Rectangle {
        radius: 16 * f.u
        color: f.tema.carta
        border.color: f.activeFocus ? f.tema.accento : f.tema.tenue
        border.width: 2
    }
}
