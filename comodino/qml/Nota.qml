import QtQuick
import QtQuick.Layouts

Text {
    property var tema
    property real u: 1
    color: tema.tenue
    font.pixelSize: 28 * u
    wrapMode: Text.WordWrap
    Layout.fillWidth: true
}
