import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Finestra per impostare la sveglia: ora, minuti, giorni, attiva/disattiva.
// È un Item (non un Popup) così ruota insieme al resto dello schermo.
Item {
    id: dlg
    property var tema
    property real u: 1
    property var giorni: []
    property bool attiva: true
    visible: false

    function open() { visible = true }
    function close() { visible = false }

    function apri() {
        var s = backend.sveglia
        tOra.currentIndex = s.ora !== undefined ? s.ora : 7
        tMin.currentIndex = s.minuto !== undefined ? s.minuto : 0
        attiva = s.attiva === undefined ? true : s.attiva
        giorni = (s.giorni || []).slice()
        open()
    }
    function toggleGiorno(i) {
        var g = giorni.slice()
        var k = g.indexOf(i)
        if (k >= 0) g.splice(k, 1); else g.push(i)
        giorni = g
    }

    Component {
        id: cifra
        Text {
            required property int index
            text: (index < 10 ? "0" : "") + index
            color: dlg.tema.testo
            font.pixelSize: 100 * dlg.u
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            opacity: 1.0 - Math.abs(Tumbler.displacement) / (Tumbler.tumbler.visibleItemCount / 2)
        }
    }

    Rectangle {      // sfondo scuro: un tocco fuori chiude
        anchors.fill: parent
        color: "#b0000000"
        MouseArea { anchors.fill: parent; onClicked: dlg.close() }
    }

    Rectangle {
        id: box
        anchors.centerIn: parent
        width: Math.min(1150 * dlg.u, parent.width - 40 * dlg.u)
        height: 860 * dlg.u
        color: dlg.tema.carta
        radius: 28 * dlg.u
        border.color: dlg.tema.accento
        border.width: 2
        MouseArea { anchors.fill: parent }   // i tocchi nel riquadro non chiudono

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 40 * dlg.u
        spacing: 30 * dlg.u

        Text {
            text: "Sveglia"
            color: dlg.tema.testo
            font.pixelSize: 50 * dlg.u
            font.weight: Font.Bold
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 24 * dlg.u
            Tumbler {
                id: tOra
                model: 24
                visibleItemCount: 3
                delegate: cifra
                Layout.preferredWidth: 220 * dlg.u
                Layout.preferredHeight: 340 * dlg.u
            }
            Text { text: ":"; color: dlg.tema.testo; font.pixelSize: 110 * dlg.u }
            Tumbler {
                id: tMin
                model: 60
                visibleItemCount: 3
                delegate: cifra
                Layout.preferredWidth: 220 * dlg.u
                Layout.preferredHeight: 340 * dlg.u
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 16 * dlg.u
            Repeater {
                model: ["L", "M", "M", "G", "V", "S", "D"]
                delegate: Rectangle {
                    required property int index
                    required property string modelData
                    readonly property bool scelto: dlg.giorni.indexOf(index) >= 0
                    width: 104 * dlg.u
                    height: width
                    radius: width / 2
                    color: scelto ? dlg.tema.accento : "transparent"
                    border.color: scelto ? dlg.tema.accento : dlg.tema.tenue
                    border.width: 2
                    Text {
                        anchors.centerIn: parent
                        text: parent.modelData
                        font.pixelSize: 42 * dlg.u
                        font.weight: Font.DemiBold
                        color: parent.scelto ? dlg.tema.sfondo : dlg.tema.testo
                    }
                    MouseArea { anchors.fill: parent; onClicked: dlg.toggleGiorno(parent.index) }
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: 20 * dlg.u
            BigButton {
                tema: dlg.tema; u: dlg.u
                text: dlg.attiva ? "✓ Attiva" : "Disattivata"
                primary: dlg.attiva
                onClicked: dlg.attiva = !dlg.attiva
            }
            Item { Layout.fillWidth: true }
            BigButton {
                tema: dlg.tema; u: dlg.u
                text: "🔔 Prova"
                onClicked: { dlg.close(); backend.provaSveglia() }
            }
            BigButton {
                tema: dlg.tema; u: dlg.u
                text: "Annulla"
                onClicked: dlg.close()
            }
            BigButton {
                tema: dlg.tema; u: dlg.u
                text: "Salva"
                primary: true
                onClicked: {
                    backend.impostaSveglia(dlg.attiva, tOra.currentIndex, tMin.currentIndex, dlg.giorni)
                    dlg.close()
                }
            }
        }
    }
}
}
