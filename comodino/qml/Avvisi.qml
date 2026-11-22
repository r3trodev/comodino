import QtQuick
import QtQuick.Layouts

// Elenco completo degli avvisi (si apre toccando l'avviso in alto) e dei terremoti recenti.
// È un Item, non un Popup, così ruota insieme al resto dello schermo.
Item {
    id: dlg
    property var tema
    property real u: 1
    property var avvisi: []
    visible: false

    readonly property var eventi: backend.terremoti.eventi || []

    function apri() { visible = true }
    function close() { visible = false }

    Rectangle {      // sfondo scuro: un tocco fuori chiude
        anchors.fill: parent
        color: "#b0000000"
        MouseArea { anchors.fill: parent; onClicked: dlg.close() }
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(1400 * dlg.u, parent.width - 60 * dlg.u)
        height: Math.min(contenuto.implicitHeight + 72 * dlg.u + 130 * dlg.u, parent.height - 60 * dlg.u)
        radius: 24 * dlg.u
        color: dlg.tema.carta
        border.width: 2
        border.color: dlg.tema.accento
        MouseArea { anchors.fill: parent }   // i tocchi nel riquadro non chiudono

        Flickable {
            id: scorri
            anchors.fill: parent
            anchors.margins: 36 * dlg.u
            anchors.bottomMargin: 130 * dlg.u
            contentHeight: contenuto.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            ColumnLayout {
                id: contenuto
                width: scorri.width
                spacing: 18 * dlg.u

                Text {
                    text: "⚠️  Avvisi"
                    color: dlg.tema.testo
                    font.pixelSize: 48 * dlg.u
                    font.weight: Font.Bold
                }
                Text {
                    visible: dlg.avvisi.length === 0
                    text: "Nessun avviso in corso."
                    color: dlg.tema.tenue
                    font.pixelSize: 32 * dlg.u
                }
                Repeater {
                    model: dlg.avvisi
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 20 * dlg.u
                        Rectangle {
                            Layout.preferredWidth: 10 * dlg.u
                            Layout.fillHeight: true
                            Layout.minimumHeight: 44 * dlg.u
                            radius: 5 * dlg.u
                            color: modelData.colore
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.testo
                            color: dlg.tema.testo
                            font.pixelSize: 32 * dlg.u
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                // tutti i terremoti del periodo, anche quelli che non fanno scattare l'avviso rosso
                Text {
                    visible: dlg.eventi.length > 0
                    Layout.topMargin: 20 * dlg.u
                    text: "🌍  Terremoti vicini (" + dlg.eventi.length + ")"
                    color: dlg.tema.testo
                    font.pixelSize: 38 * dlg.u
                    font.weight: Font.Bold
                }
                Repeater {
                    model: dlg.eventi
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 24 * dlg.u
                        Text {
                            Layout.preferredWidth: 130 * dlg.u
                            text: "M" + modelData.mag
                            color: modelData.forte ? "#f85149" : dlg.tema.accento
                            font.family: "DejaVu Sans Mono"
                            font.pixelSize: 34 * dlg.u
                            font.weight: Font.Bold
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                Layout.fillWidth: true
                                text: modelData.luogo
                                color: dlg.tema.testo
                                font.pixelSize: 30 * dlg.u
                                elide: Text.ElideRight
                            }
                            Text {
                                text: modelData.giorno + " " + modelData.ora + " · " + modelData.km + " km da casa · profondità "
                                      + modelData.prof + " km"
                                color: dlg.tema.tenue
                                font.pixelSize: 24 * dlg.u
                            }
                        }
                    }
                }
            }
        }

        BigButton {
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottomMargin: 24 * dlg.u
            text: "Chiudi"
            tema: dlg.tema
            u: dlg.u
            primary: true
            onClicked: dlg.close()
        }
    }
}
