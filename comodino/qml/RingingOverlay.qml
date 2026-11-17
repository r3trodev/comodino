import QtQuick
import QtQuick.Layouts

// Schermata a tutto schermo mentre la sveglia suona.
// "Rimanda" è enorme e facile da colpire; per spegnere bisogna tenere premuto,
// così da mezzo addormentati non la si spegne per sbaglio.
Rectangle {
    id: ov
    property var tema
    property real u: 1
    property date adesso: new Date()

    color: "#000000"
    visible: backend.sveglia.suona === true

    MouseArea { anchors.fill: parent }   // blocca i tocchi sotto

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 48 * ov.u

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: Qt.formatTime(ov.adesso, "HH:mm")
            color: "#ffb347"
            font.pixelSize: 260 * ov.u
            font.weight: Font.Light
            SequentialAnimation on opacity {
                running: ov.visible
                loops: Animation.Infinite
                NumberAnimation { to: 0.55; duration: 900; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
            }
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: {
                var m = backend.meteo
                var nome = backend.sveglia.suona_nome ? backend.sveglia.suona_nome + "  ·  " : ""
                return nome + (m.temp !== undefined ? "Buongiorno!  " + m.icona + "  " + m.temp + "°  " + m.descrizione
                                                    : "Buongiorno!")
            }
            color: "#e6edf3"
            font.pixelSize: 54 * ov.u
        }

        BigButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 950 * ov.u
            Layout.preferredHeight: 230 * ov.u
            tema: ov.tema; u: ov.u
            primary: true
            fontSize: 72 * ov.u
            text: "😴  Rimanda"
            onClicked: backend.snooze()
        }

        Rectangle {
            id: holdBox
            property real frac: 0
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 950 * ov.u
            Layout.preferredHeight: 140 * ov.u
            radius: 20 * ov.u
            color: "transparent"
            border.color: "#8b949e"
            border.width: 2
            clip: true

            Rectangle {
                width: parent.width * holdBox.frac
                height: parent.height
                radius: parent.radius
                color: "#da3633"
            }
            Text {
                anchors.centerIn: parent
                text: "Tieni premuto per spegnere"
                color: "#e6edf3"
                font.pixelSize: 42 * ov.u
            }
            NumberAnimation {
                id: fill
                target: holdBox; property: "frac"
                from: 0; to: 1; duration: 1500
            }
            MouseArea {
                anchors.fill: parent
                pressAndHoldInterval: 1500
                onPressed: fill.restart()
                onReleased: { fill.stop(); holdBox.frac = 0 }
                onCanceled: { fill.stop(); holdBox.frac = 0 }
                onPressAndHold: { holdBox.frac = 0; backend.stop() }
            }
        }
    }
}
