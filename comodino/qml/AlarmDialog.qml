import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Sveglie: elenco (attiva/spegni, pisolino, alba simulata) ed editor di una sveglia.
// È un Item (non un Popup) così ruota insieme al resto dello schermo.
Item {
    id: dlg
    property var tema
    property real u: 1
    visible: false

    // editor
    property bool modifica: false
    property string svId: ""
    property var giorni: []
    property bool attiva: true

    readonly property var s: backend.sveglia
    readonly property var nomiGiorni: ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]

    function apri() { modifica = false; visible = true }
    function open() { apri() }
    function close() { Qt.inputMethod.hide(); visible = false }

    function pad(n) { return (n < 10 ? "0" : "") + n }
    function giorniTesto(sv) {
        if (sv.data) {
            var d = new Date(sv.data + "T00:00")
            return "Una volta: " + nomiGiorni[(d.getDay() + 6) % 7].toLowerCase() + " " + d.getDate()
        }
        var g = sv.giorni || []
        if (g.length === 0) return "Una volta"
        var k = g.slice().sort().join(",")
        if (k === "0,1,2,3,4") return "Lun–Ven"
        if (k === "5,6") return "Weekend"
        if (k === "0,1,2,3,4,5,6") return "Tutti i giorni"
        return g.slice().sort().map(function (i) { return dlg.nomiGiorni[i] }).join(" ")
    }
    function nuova() {
        svId = ""; nome.text = "Sveglia"; attiva = true; giorni = [0, 1, 2, 3, 4]
        tOra.currentIndex = 7; tMin.currentIndex = 0
        modifica = true
    }
    function modificaSveglia(sv) {
        svId = sv.id; nome.text = sv.nome; attiva = true; giorni = (sv.giorni || []).slice()
        tOra.currentIndex = sv.ora; tMin.currentIndex = sv.minuto
        modifica = true
    }
    function toggleGiorno(i) {
        var g = giorni.slice()
        var k = g.indexOf(i)
        if (k >= 0) g.splice(k, 1); else g.push(i)
        giorni = g
    }
    function salva() {
        backend.salvaSveglia({ id: svId, nome: nome.text, attiva: attiva,
                               ora: tOra.currentIndex, minuto: tMin.currentIndex, giorni: giorni })
        Qt.inputMethod.hide()
        modifica = false
    }

    Rectangle {      // sfondo scuro: un tocco fuori chiude
        anchors.fill: parent
        color: "#b0000000"
        MouseArea { anchors.fill: parent; onClicked: dlg.close() }
    }

    Component {
        id: cifra
        Text {
            required property int index
            text: (index < 10 ? "0" : "") + index
            color: dlg.tema.testo
            font.pixelSize: 96 * dlg.u
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            opacity: 1.0 - Math.abs(Tumbler.displacement) / (Tumbler.tumbler.visibleItemCount / 2)
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(1300 * dlg.u, parent.width - 40 * dlg.u)
        height: Math.min(1020 * dlg.u, parent.height - 40 * dlg.u)
        color: dlg.tema.carta
        radius: 28 * dlg.u
        border.color: dlg.tema.accento
        border.width: 2
        MouseArea { anchors.fill: parent }   // i tocchi nel riquadro non chiudono

        // ================================================ ELENCO
        ColumnLayout {
            visible: !dlg.modifica
            anchors.fill: parent
            anchors.margins: 36 * dlg.u
            spacing: 18 * dlg.u

            RowLayout {
                Layout.fillWidth: true
                Text { text: "⏰  Sveglie"; color: dlg.tema.testo; font.pixelSize: 48 * dlg.u; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                BigButton { tema: dlg.tema; u: dlg.u; text: "＋  Nuova"; primary: true; onClicked: dlg.nuova() }
            }

            ListView {
                id: elenco
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 10 * dlg.u
                model: (dlg.s.sveglie || []).concat(dlg.s.telefono ? [dlg.s.telefono] : [])
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool tel: modelData.id === "telefono"
                    width: elenco.width
                    height: 118 * dlg.u
                    radius: 18 * dlg.u
                    color: "transparent"
                    border.width: 1
                    border.color: dlg.tema.tenue
                    opacity: modelData.attiva ? 1 : 0.5
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 28 * dlg.u
                        anchors.rightMargin: 16 * dlg.u
                        spacing: 26 * dlg.u
                        Text {
                            text: dlg.pad(parent.parent.modelData.ora) + ":" + dlg.pad(parent.parent.modelData.minuto)
                            color: dlg.tema.testo
                            font.pixelSize: 66 * dlg.u
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                text: (parent.parent.parent.tel ? "📱 " : "") + parent.parent.parent.modelData.nome
                                color: dlg.tema.testo
                                font.pixelSize: 32 * dlg.u
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: parent.parent.parent.tel ? "Si cambia da Home Assistant" : dlg.giorniTesto(parent.parent.parent.modelData)
                                color: dlg.tema.tenue
                                font.pixelSize: 26 * dlg.u
                            }
                        }
                        BigButton {
                            visible: !parent.parent.tel
                            tema: dlg.tema; u: dlg.u
                            implicitHeight: 84 * dlg.u
                            text: parent.parent.modelData.attiva ? "Attiva" : "Spenta"
                            primary: parent.parent.modelData.attiva
                            onClicked: backend.attivaSveglia(parent.parent.modelData.id, !parent.parent.modelData.attiva)
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        anchors.rightMargin: 200 * dlg.u     // il pulsante Attiva/Spenta resta cliccabile
                        enabled: !parent.tel
                        onClicked: dlg.modificaSveglia(parent.modelData)
                    }
                }
            }
            Text {
                visible: elenco.count === 0
                text: "Nessuna sveglia: tocca «Nuova»."
                color: dlg.tema.tenue
                font.pixelSize: 30 * dlg.u
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 16 * dlg.u
                Text { text: "😴 Pisolino"; color: dlg.tema.testo; font.pixelSize: 30 * dlg.u }
                Repeater {
                    model: [10, 20, 30]
                    delegate: BigButton {
                        required property int modelData
                        tema: dlg.tema; u: dlg.u
                        implicitHeight: 84 * dlg.u
                        text: modelData + " min"
                        onClicked: { backend.pisolino(modelData); dlg.close() }
                    }
                }
                Item { Layout.fillWidth: true }
                Text { text: "🌅 Alba"; color: dlg.tema.testo; font.pixelSize: 30 * dlg.u }
                Numero {
                    tema: dlg.tema; u: dlg.u
                    valore: backend.impostazioni.alba_min
                    minimo: 0; massimo: 60; passo: 5; suffisso: "′"
                    onCambiato: (v) => backend.impostaAlba(v)
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: backend.impostazioni.alba_min > 0
                          ? "Lo schermo si illumina piano " + backend.impostazioni.alba_min + " minuti prima di ogni sveglia."
                          : "Alba simulata spenta."
                    color: dlg.tema.tenue
                    font.pixelSize: 24 * dlg.u
                    wrapMode: Text.WordWrap
                }
                BigButton { tema: dlg.tema; u: dlg.u; text: "Chiudi"; onClicked: dlg.close() }
            }
        }

        // ================================================ MODIFICA
        ColumnLayout {
            visible: dlg.modifica
            anchors.fill: parent
            anchors.margins: 36 * dlg.u
            spacing: 22 * dlg.u

            RowLayout {
                Layout.fillWidth: true
                spacing: 20 * dlg.u
                Text { text: dlg.svId ? "Modifica sveglia" : "Nuova sveglia"; color: dlg.tema.testo; font.pixelSize: 44 * dlg.u; font.weight: Font.Bold }
                Campo {
                    id: nome
                    tema: dlg.tema; u: dlg.u
                    Layout.fillWidth: true
                    maximumLength: 30
                    placeholderText: "Nome (es. Lavoro)"
                }
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 24 * dlg.u
                Tumbler {
                    id: tOra
                    model: 24
                    visibleItemCount: 3
                    delegate: cifra
                    Layout.preferredWidth: 210 * dlg.u
                    Layout.preferredHeight: 320 * dlg.u
                }
                Text { text: ":"; color: dlg.tema.testo; font.pixelSize: 100 * dlg.u }
                Tumbler {
                    id: tMin
                    model: 60
                    visibleItemCount: 3
                    delegate: cifra
                    Layout.preferredWidth: 210 * dlg.u
                    Layout.preferredHeight: 320 * dlg.u
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
                        width: 100 * dlg.u
                        height: width
                        radius: width / 2
                        color: scelto ? dlg.tema.accento : "transparent"
                        border.color: scelto ? dlg.tema.accento : dlg.tema.tenue
                        border.width: 2
                        Text {
                            anchors.centerIn: parent
                            text: parent.modelData
                            font.pixelSize: 40 * dlg.u
                            font.weight: Font.DemiBold
                            color: parent.scelto ? dlg.tema.sfondo : dlg.tema.testo
                        }
                        MouseArea { anchors.fill: parent; onClicked: dlg.toggleGiorno(parent.index) }
                    }
                }
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: dlg.giorni.length ? " " : "Nessun giorno scelto: suonerà una volta sola, alla prossima occasione."
                color: dlg.tema.tenue
                font.pixelSize: 26 * dlg.u
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: 18 * dlg.u
                BigButton {
                    visible: dlg.svId !== ""
                    tema: dlg.tema; u: dlg.u
                    text: "🗑  Elimina"
                    onClicked: { backend.eliminaSveglia(dlg.svId); dlg.modifica = false }
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
                    onClicked: { Qt.inputMethod.hide(); dlg.modifica = false }
                }
                BigButton {
                    tema: dlg.tema; u: dlg.u
                    text: "Salva"
                    primary: true
                    onClicked: dlg.salva()
                }
            }
        }
    }
}
