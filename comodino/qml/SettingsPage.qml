import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Temi.js" as Temi

// Pannello impostazioni a schede: Stato, Wi-Fi, Luogo, Schermo, Tema, Batteria, Casa, Da PC, Aggiorna.
Rectangle {
    id: pag
    property var tema
    property real u: 1
    property int scheda: 0
    property var esiti: ({})            // ultimo risultato ricevuto, per nome
    property string ssidScelto: ""
    property bool ssidProtetta: false
    property bool conferma: false        // doppio tocco per riavvio/spegnimento
    property bool sceltaPresa: false     // elenco prese di Home Assistant aperto
    property bool sceltaZona: false      // elenco zone delle allerte meteo aperto
    readonly property var imp: backend.impostazioni

    color: tema.sfondo
    visible: false

    function apri() {
        visible = true
        scheda = 0
        esiti = ({})
        ssidScelto = ""
        backend.wifiStato()
        backend.diagnostica()
    }
    function chiudi() {
        Qt.inputMethod.hide()
        visible = false
        conferma = false
        sceltaPresa = false
        sceltaZona = false
    }
    function azzera(nome) {
        var e = Object.assign({}, esiti)
        delete e[nome]
        esiti = e
    }

    Connections {
        target: backend
        function onRisultato(nome, dati) {
            var e = Object.assign({}, pag.esiti)
            e[nome] = dati
            pag.esiti = e
            if (nome === "prese" && dati.ok) pag.sceltaPresa = true
            if (nome === "zone_allerte" && dati.ok) pag.sceltaZona = true
            if (nome === "wifi_connetti" && dati.ok) {
                pag.ssidScelto = ""
                backend.wifiStato()
            }
        }
    }

    MouseArea { anchors.fill: parent }   // blocca i tocchi verso la schermata sotto

    RowLayout {
        anchors.fill: parent
        anchors.margins: 36 * pag.u
        spacing: 36 * pag.u

        // ------------------------------------------------ schede
        ColumnLayout {
            Layout.preferredWidth: 360 * pag.u
            Layout.fillHeight: true
            spacing: 10 * pag.u

            Titolo { tema: pag.tema; u: pag.u; text: "⚙️  Impostazioni"; Layout.bottomMargin: 6 * pag.u }
            Repeater {
                model: ["🩺  Stato", "📶  Wi-Fi", "📍  Luogo", "🖥️  Schermo", "🎨  Tema", "🔋  Batteria", "🏠  Casa", "🖧  Server", "💻  Da PC", "⬆️  Aggiorna"]
                delegate: BigButton {
                    required property int index
                    required property string modelData
                    tema: pag.tema; u: pag.u
                    Layout.fillWidth: true
                    implicitHeight: 76 * pag.u
                    fontSize: 29 * pag.u
                    text: modelData
                    primary: pag.scheda === index
                    onClicked: { Qt.inputMethod.hide(); pag.scheda = index }
                }
            }
            Item { Layout.fillHeight: true }
            BigButton {
                tema: pag.tema; u: pag.u
                Layout.fillWidth: true
                implicitHeight: 76 * pag.u
                text: "✕  Chiudi"
                onClicked: pag.chiudi()
            }
        }

        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 2; color: pag.tema.tenue; opacity: 0.4 }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: pag.scheda

            // ============================================ STATO
            ColumnLayout {
                spacing: 18 * pag.u
                RowLayout {
                    Layout.fillWidth: true
                    Titolo { tema: pag.tema; u: pag.u; text: "Verifica" }
                    Item { Layout.fillWidth: true }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: "↻  Ripeti verifica"
                        onClicked: { pag.azzera("diagnostica"); backend.diagnostica() }
                    }
                }
                Nota { tema: pag.tema; u: pag.u; visible: !pag.esiti.diagnostica; text: "Verifica in corso…" }
                Repeater {
                    model: pag.esiti.diagnostica ? pag.esiti.diagnostica.voci : []
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 20 * pag.u
                        Text {
                            text: parent.modelData.ok === true ? "✅" : (parent.modelData.ok === false ? "❌" : "➖")
                            font.pixelSize: 36 * pag.u
                        }
                        Text {
                            text: parent.modelData.voce
                            color: pag.tema.testo
                            font.pixelSize: 32 * pag.u
                            font.weight: Font.DemiBold
                            Layout.preferredWidth: 340 * pag.u
                        }
                        Text {
                            text: parent.modelData.dettaglio
                            color: pag.tema.tenue
                            font.pixelSize: 28 * pag.u
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
                Item { Layout.fillHeight: true }
                RowLayout {
                    spacing: 20 * pag.u
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: pag.conferma ? "Tocca di nuovo: RIAVVIA" : "🔄  Riavvia tablet"
                        onClicked: pag.conferma ? backend.riavvia() : pag.conferma = true
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: pag.conferma ? "Tocca di nuovo: SPEGNI" : "⏻  Spegni"
                        onClicked: pag.conferma ? backend.spegni() : pag.conferma = true
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        visible: pag.conferma
                        text: "Annulla"
                        onClicked: pag.conferma = false
                    }
                }
            }

            // ============================================ WI-FI
            ColumnLayout {
                spacing: 18 * pag.u
                Titolo { tema: pag.tema; u: pag.u; text: "Wi-Fi" }
                Nota {
                    tema: pag.tema; u: pag.u
                    color: pag.esiti.wifi_stato && pag.esiti.wifi_stato.connesso ? "#3fb950" : pag.tema.tenue
                    text: {
                        var s = pag.esiti.wifi_stato
                        if (!s) return "Controllo connessione…"
                        return s.connesso ? "Connesso a " + s.ssid + " · segnale " + s.segnale + "% · IP " + s.ip
                                          : "Non connesso"
                    }
                }

                // rete scelta + password: in alto, così la tastiera non la copre
                RowLayout {
                    visible: pag.ssidScelto !== ""
                    Layout.fillWidth: true
                    spacing: 18 * pag.u
                    Text {
                        text: pag.ssidScelto
                        color: pag.tema.testo
                        font.pixelSize: 34 * pag.u
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        Layout.maximumWidth: 380 * pag.u
                    }
                    Campo {
                        id: pw
                        tema: pag.tema; u: pag.u
                        visible: pag.ssidProtetta
                        placeholderText: "Password"
                        echoMode: TextInput.Password
                        Layout.fillWidth: true
                        onAccepted: connetti.clicked()
                    }
                    Item { visible: !pag.ssidProtetta; Layout.fillWidth: true }
                    BigButton {
                        id: connetti
                        tema: pag.tema; u: pag.u
                        primary: true
                        text: "Connetti"
                        onClicked: {
                            Qt.inputMethod.hide()
                            pag.azzera("wifi_connetti")
                            pag.esiti = Object.assign({}, pag.esiti, { wifi_connetti: { ok: null, messaggio: "Connessione…" } })
                            backend.wifiConnetti(pag.ssidScelto, pw.text)
                        }
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !!pag.esiti.wifi_connetti
                    color: !pag.esiti.wifi_connetti ? pag.tema.tenue
                           : (pag.esiti.wifi_connetti.ok === true ? "#3fb950"
                              : (pag.esiti.wifi_connetti.ok === false ? "#f85149" : pag.tema.tenue))
                    text: pag.esiti.wifi_connetti ? (pag.esiti.wifi_connetti.messaggio || pag.esiti.wifi_connetti.errore || "") : ""
                }

                RowLayout {
                    spacing: 20 * pag.u
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: "🔍  Cerca reti"
                        onClicked: {
                            pag.esiti = Object.assign({}, pag.esiti, { wifi_reti: { ok: null, reti: [] } })
                            backend.wifiScansiona()
                        }
                    }
                    Nota {
                        tema: pag.tema; u: pag.u
                        text: !pag.esiti.wifi_reti ? "" : (pag.esiti.wifi_reti.ok === null ? "Ricerca in corso…"
                              : (pag.esiti.wifi_reti.ok ? pag.esiti.wifi_reti.reti.length + " reti trovate" : pag.esiti.wifi_reti.errore))
                    }
                }
                ListView {
                    id: reti
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8 * pag.u
                    model: pag.esiti.wifi_reti ? pag.esiti.wifi_reti.reti : []
                    delegate: Rectangle {
                        required property var modelData
                        width: reti.width
                        height: 88 * pag.u
                        radius: 14 * pag.u
                        color: pag.ssidScelto === modelData.ssid ? pag.tema.carta : "transparent"
                        border.color: pag.tema.tenue
                        border.width: 1
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 24 * pag.u
                            anchors.rightMargin: 24 * pag.u
                            Text {
                                text: (parent.parent.modelData.attiva ? "✓  " : "") + parent.parent.modelData.ssid
                                color: pag.tema.testo
                                font.pixelSize: 34 * pag.u
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: (parent.parent.modelData.protetta ? "🔒  " : "") + parent.parent.modelData.segnale + "%"
                                color: pag.tema.tenue
                                font.pixelSize: 30 * pag.u
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                pag.ssidScelto = parent.modelData.ssid
                                pag.ssidProtetta = parent.modelData.protetta
                                pag.azzera("wifi_connetti")
                                pw.text = ""
                                if (parent.modelData.protetta) pw.forceActiveFocus()
                            }
                        }
                    }
                }
            }

            // ============================================ LUOGO
            ColumnLayout {
                spacing: 18 * pag.u
                Titolo { tema: pag.tema; u: pag.u; text: "Luogo per il meteo" }
                Nota {
                    tema: pag.tema; u: pag.u
                    text: "Attuale: " + pag.imp.citta + "  (" + pag.imp.lat + ", " + pag.imp.lon + ")"
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18 * pag.u
                    Campo {
                        id: q
                        tema: pag.tema; u: pag.u
                        placeholderText: "Città o paese…"
                        Layout.fillWidth: true
                        onAccepted: cerca.clicked()
                    }
                    BigButton {
                        id: cerca
                        tema: pag.tema; u: pag.u
                        primary: true
                        text: "Cerca"
                        onClicked: {
                            Qt.inputMethod.hide()
                            pag.esiti = Object.assign({}, pag.esiti, { luogo: { ok: null, risultati: [] } })
                            backend.cercaLuogo(q.text)
                        }
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !!pag.esiti.luogo && pag.esiti.luogo.ok !== true
                    text: !pag.esiti.luogo ? "" : (pag.esiti.luogo.ok === null ? "Ricerca…" : pag.esiti.luogo.errore)
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18 * pag.u
                    Nota {
                        tema: pag.tema; u: pag.u
                        text: "⚠️ Zona allerte meteo: " + (pag.imp.zona_allerte || "non scelta")
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: "Scegli zona…"
                        onClicked: {
                            pag.esiti = Object.assign({}, pag.esiti, { zone_allerte: { ok: null } })
                            filtroZona.text = ""
                            backend.cercaZoneAllerte()
                        }
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !!pag.esiti.zone_allerte && pag.esiti.zone_allerte.ok !== true
                    color: pag.esiti.zone_allerte && pag.esiti.zone_allerte.ok === false ? "#f85149" : pag.tema.tenue
                    text: !pag.esiti.zone_allerte ? "" : (pag.esiti.zone_allerte.ok === null ? "Scarico l'elenco delle zone da Meteoalarm…" : pag.esiti.zone_allerte.errore)
                }
                Campo {
                    id: filtroZona
                    visible: pag.sceltaZona
                    tema: pag.tema; u: pag.u
                    Layout.fillWidth: true
                    placeholderText: "Filtra (es. Palermo, Sicilia)…"
                }
                ListView {
                    id: zone
                    visible: pag.sceltaZona
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 6 * pag.u
                    model: {
                        var z = pag.esiti.zone_allerte && pag.esiti.zone_allerte.ok ? pag.esiti.zone_allerte.zone : []
                        var f = filtroZona.text.toLowerCase()
                        return f ? z.filter(function (x) { return x.toLowerCase().indexOf(f) >= 0 }) : z
                    }
                    delegate: Rectangle {
                        required property string modelData
                        width: zone.width
                        height: 78 * pag.u
                        radius: 12 * pag.u
                        color: pag.imp.zona_allerte === modelData ? pag.tema.carta : "transparent"
                        border.color: pag.tema.tenue
                        border.width: 1
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            x: 24 * pag.u
                            text: parent.modelData
                            color: pag.tema.testo
                            font.pixelSize: 30 * pag.u
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: { backend.impostaZonaAllerte(parent.modelData); pag.sceltaZona = false; Qt.inputMethod.hide() }
                        }
                    }
                }
                ListView {
                    id: luoghi
                    visible: !pag.sceltaZona
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8 * pag.u
                    model: pag.esiti.luogo && pag.esiti.luogo.ok ? pag.esiti.luogo.risultati : []
                    delegate: Rectangle {
                        required property var modelData
                        width: luoghi.width
                        height: 100 * pag.u
                        radius: 14 * pag.u
                        color: "transparent"
                        border.color: pag.tema.tenue
                        border.width: 1
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            x: 24 * pag.u
                            Text { text: parent.parent.modelData.nome; color: pag.tema.testo; font.pixelSize: 34 * pag.u; font.weight: Font.DemiBold }
                            Text { text: parent.parent.modelData.dettaglio; color: pag.tema.tenue; font.pixelSize: 26 * pag.u }
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                var m = parent.modelData
                                backend.impostaLuogo(m.nome, m.lat, m.lon, m.fuso)
                                pag.azzera("luogo")
                                q.text = ""
                            }
                        }
                    }
                }
            }

            // ============================================ SCHERMO
            ColumnLayout {
                spacing: 20 * pag.u
                Titolo { tema: pag.tema; u: pag.u; text: "Orientamento" }
                Nota { tema: pag.tema; u: pag.u; text: "Tocca le opzioni finché lo schermo non è dritto. Il touch segue in automatico." }
                RowLayout {
                    spacing: 18 * pag.u
                    Repeater {
                        model: [0, 90, 180, 270]
                        delegate: BigButton {
                            required property int modelData
                            tema: pag.tema; u: pag.u
                            implicitWidth: 170 * pag.u
                            text: modelData + "°"
                            primary: backend.rotazione === modelData
                            onClicked: backend.impostaRotazione(modelData)
                        }
                    }
                }

                Titolo { tema: pag.tema; u: pag.u; text: "Luminosità"; Layout.topMargin: 20 * pag.u }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 20 * pag.u
                    Text { text: "Giorno"; color: pag.tema.testo; font.pixelSize: 32 * pag.u; Layout.preferredWidth: 160 * pag.u }
                    Slider {
                        id: lumG
                        from: 5; to: 100; stepSize: 5
                        value: pag.imp.luminosita_giorno
                        Layout.fillWidth: true
                        onPressedChanged: if (!pressed) backend.impostaLuminosita(lumG.value, lumN.value)
                    }
                    Text { text: Math.round(lumG.value) + "%"; color: pag.tema.tenue; font.pixelSize: 30 * pag.u; Layout.preferredWidth: 110 * pag.u }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 20 * pag.u
                    Text { text: "Notte"; color: pag.tema.testo; font.pixelSize: 32 * pag.u; Layout.preferredWidth: 160 * pag.u }
                    Slider {
                        id: lumN
                        from: 1; to: 40; stepSize: 1
                        value: pag.imp.luminosita_notte
                        Layout.fillWidth: true
                        onPressedChanged: if (!pressed) backend.impostaLuminosita(lumG.value, lumN.value)
                    }
                    Text { text: Math.round(lumN.value) + "%"; color: pag.tema.tenue; font.pixelSize: 30 * pag.u; Layout.preferredWidth: 110 * pag.u }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18 * pag.u
                    readonly property var bl: backend.luminosita
                    Nota {
                        tema: pag.tema; u: pag.u
                        color: parent.bl.errore || !parent.bl.dispositivo ? "#f85149" : pag.tema.tenue
                        text: !parent.bl.dispositivo ? "⚠️ " + parent.bl.errore
                              : "Dispositivo: " + parent.bl.dispositivo + " (" + parent.bl.tipo + ")"
                                + (parent.bl.metodo ? " · via " + parent.bl.metodo : "")
                                + (parent.bl.errore ? "  ⚠️ " + parent.bl.errore : "")
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        visible: parent.bl.alternative && parent.bl.alternative.length > 1
                        text: "Cambia dispositivo"
                        onClicked: backend.prossimaRetroilluminazione()
                    }
                }

                Titolo { tema: pag.tema; u: pag.u; text: "Modalità notte"; Layout.topMargin: 20 * pag.u }
                RowLayout {
                    spacing: 24 * pag.u
                    Text { text: "Dalle"; color: pag.tema.testo; font.pixelSize: 32 * pag.u }
                    Orario {
                        tema: pag.tema; u: pag.u
                        valore: pag.imp.notte_inizio
                        onCambiato: (v) => backend.impostaNotte(v, pag.imp.notte_fine)
                    }
                    Text { text: "alle"; color: pag.tema.testo; font.pixelSize: 32 * pag.u }
                    Orario {
                        tema: pag.tema; u: pag.u
                        valore: pag.imp.notte_fine
                        onCambiato: (v) => backend.impostaNotte(pag.imp.notte_inizio, v)
                    }
                }
                Item { Layout.fillHeight: true }
            }

            // ============================================ TEMA
            ColumnLayout {
                spacing: 18 * pag.u
                Titolo { tema: pag.tema; u: pag.u; text: "Layout" }
                RowLayout {
                    spacing: 18 * pag.u
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: "Classico"
                        primary: pag.imp.layout !== "stazione"
                        onClicked: backend.impostaLayout("classico")
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: "Stazione"
                        primary: pag.imp.layout === "stazione"
                        onClicked: backend.impostaLayout("stazione")
                    }
                    Nota {
                        tema: pag.tema; u: pag.u
                        text: "Stazione: tre colonne con dettagli, aria e settimana. Sta bene con il tema E-ink."
                    }
                }
                Titolo { tema: pag.tema; u: pag.u; text: "Tema"; Layout.topMargin: 6 * pag.u }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 4
                    columnSpacing: 16 * pag.u
                    rowSpacing: 16 * pag.u
                    Repeater {
                        model: Temi.ORDINE
                        delegate: Rectangle {
                            id: anteprima
                            required property string modelData
                            readonly property var t: Temi.TEMI[modelData]
                            readonly property bool scelto: pag.imp.tema === modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 150 * pag.u
                            radius: 18 * pag.u
                            color: t.sfondo
                            border.width: scelto ? 5 : 1
                            border.color: scelto ? pag.tema.accento : pag.tema.tenue
                            Text {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.margins: 18 * pag.u
                                text: anteprima.t.nome + (anteprima.scelto ? "  ✓" : "")
                                color: anteprima.t.testo
                                font.pixelSize: 30 * pag.u
                                font.weight: Font.DemiBold
                            }
                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.margins: 16 * pag.u
                                height: 60 * pag.u
                                radius: 12 * pag.u
                                color: anteprima.t.carta
                                Row {
                                    anchors.centerIn: parent
                                    spacing: 14 * pag.u
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 26 * pag.u; height: width; radius: width / 2
                                        color: anteprima.t.accento
                                    }
                                    Text { text: "07:30"; color: anteprima.t.testo; font.pixelSize: 28 * pag.u }
                                    Text { text: "Agenda"; color: anteprima.t.tenue; font.pixelSize: 24 * pag.u; anchors.verticalCenter: parent.verticalCenter }
                                }
                            }
                            MouseArea { anchors.fill: parent; onClicked: backend.impostaTema(anteprima.modelData) }
                        }
                    }
                }

                Titolo { tema: pag.tema; u: pag.u; text: "Stile notte"; Layout.topMargin: 14 * pag.u }
                Nota { tema: pag.tema; u: pag.u; text: "Colori quando lo schermo è al minimo. Rosso e ambra disturbano meno il sonno." }
                RowLayout {
                    spacing: 18 * pag.u
                    Repeater {
                        model: Temi.ORDINE_NOTTE
                        delegate: BigButton {
                            required property string modelData
                            tema: pag.tema; u: pag.u
                            text: Temi.NOTTE[modelData].nome
                            primary: pag.imp.notte_stile === modelData
                            onClicked: backend.impostaStileNotte(modelData)
                        }
                    }
                }
                Item { Layout.fillHeight: true }
            }

            // ============================================ BATTERIA
            ColumnLayout {
                id: tabBatt
                spacing: 16 * pag.u
                readonly property var b: backend.batteria
                readonly property var metodi: ({
                    "kernel": "Limite di carica hardware: la carica si ferma da sola al massimo impostato.",
                    "presa": "Presa smart: il Comodino accende la presa sotto il minimo e la spegne sopra il massimo.",
                    "lettura": "Solo lettura: scegli una presa smart qui sotto per gestire la carica.",
                    "disattivata": "Gestione disattivata: il tablet si carica sempre al 100%.",
                    "assente": "Batteria non rilevata."
                })

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 30 * pag.u
                    Text {
                        text: tabBatt.b.presente ? tabBatt.b.percentuale + "%" : "--"
                        color: tabBatt.b.avviso ? "#f85149" : pag.tema.testo
                        font.pixelSize: 120 * pag.u
                        font.weight: Font.Light
                    }
                    ColumnLayout {
                        spacing: 4 * pag.u
                        Layout.fillWidth: true
                        Text {
                            text: tabBatt.b.presente ? (tabBatt.b.alimentato ? "⚡ " : "🔋 ") + tabBatt.b.stato_it : "Batteria non rilevata"
                            color: pag.tema.testo
                            font.pixelSize: 36 * pag.u
                        }
                        Nota {
                            tema: pag.tema; u: pag.u
                            visible: !!tabBatt.b.presente
                            text: (tabBatt.b.temperatura !== null && tabBatt.b.temperatura !== undefined ? "Batteria " + tabBatt.b.temperatura + " °C" : "Temp. batteria non disponibile")
                                  + (tabBatt.b.temp_processore !== null && tabBatt.b.temp_processore !== undefined
                                     ? "  ·  Processore " + tabBatt.b.temp_processore + " °C" + (tabBatt.b.caldo ? " 🔥" : "") : "")
                                  + (tabBatt.b.salute ? "  ·  Salute: " + tabBatt.b.salute : "")
                        }
                        Nota {
                            tema: pag.tema; u: pag.u
                            visible: !!tabBatt.b.azione
                            text: "Ultima azione: " + (tabBatt.b.azione || "")
                        }
                        Nota {
                            tema: pag.tema; u: pag.u
                            visible: !!tabBatt.b.errore
                            color: "#f85149"
                            text: "⚠️ " + (tabBatt.b.errore || "")
                        }
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: pag.imp.batt_gestione ? "Gestione attiva" : "Gestione spenta"
                        primary: pag.imp.batt_gestione
                        onClicked: backend.gestioneBatteria(!pag.imp.batt_gestione)
                    }
                }
                Nota { tema: pag.tema; u: pag.u; text: tabBatt.metodi[tabBatt.b.metodo || "assente"] || "" }

                Titolo { tema: pag.tema; u: pag.u; text: "Soglie"; Layout.topMargin: 10 * pag.u }
                GridLayout {
                    columns: 2
                    columnSpacing: 30 * pag.u
                    rowSpacing: 10 * pag.u
                    Text { text: "Ricarica sotto il"; color: pag.tema.testo; font.pixelSize: 32 * pag.u }
                    Numero {
                        tema: pag.tema; u: pag.u
                        valore: pag.imp.batt_min; minimo: 20; massimo: pag.imp.batt_max - 10
                        onCambiato: (v) => backend.impostaBatteria(v, pag.imp.batt_max, pag.imp.batt_allarme)
                    }
                    Text { text: "Smetti di caricare al"; color: pag.tema.testo; font.pixelSize: 32 * pag.u }
                    Numero {
                        tema: pag.tema; u: pag.u
                        valore: pag.imp.batt_max; minimo: pag.imp.batt_min + 10; massimo: 100
                        onCambiato: (v) => backend.impostaBatteria(pag.imp.batt_min, v, pag.imp.batt_allarme)
                    }
                    Text { text: "Avviso sotto il"; color: pag.tema.testo; font.pixelSize: 32 * pag.u }
                    Numero {
                        tema: pag.tema; u: pag.u
                        valore: pag.imp.batt_allarme; minimo: 5; massimo: pag.imp.batt_min - 5
                        onCambiato: (v) => backend.impostaBatteria(pag.imp.batt_min, pag.imp.batt_max, v)
                    }
                }

                Titolo { tema: pag.tema; u: pag.u; text: "Presa del caricatore"; Layout.topMargin: 10 * pag.u; visible: tabBatt.b.metodo !== "kernel" }
                RowLayout {
                    visible: tabBatt.b.metodo !== "kernel"
                    Layout.fillWidth: true
                    spacing: 18 * pag.u
                    Nota {
                        tema: pag.tema; u: pag.u
                        color: pag.imp.batt_presa ? pag.tema.testo : pag.tema.tenue
                        text: pag.imp.batt_presa ? pag.imp.batt_presa : "Nessuna presa scelta"
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: "Scegli…"
                        onClicked: { pag.azzera("prese"); backend.cercaPrese() }
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        visible: !!pag.imp.batt_presa
                        text: "Accendi"
                        onClicked: { pag.azzera("presa"); backend.provaPresa(true) }
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        visible: !!pag.imp.batt_presa
                        text: "Spegni"
                        onClicked: { pag.azzera("presa"); backend.provaPresa(false) }
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    readonly property var e: pag.esiti.presa || (pag.esiti.prese && !pag.esiti.prese.ok ? pag.esiti.prese : null)
                    visible: !!e
                    color: e && e.ok ? "#3fb950" : "#f85149"
                    text: e ? (e.messaggio || e.errore || "") : ""
                }
                ListView {
                    id: listaPrese
                    visible: pag.sceltaPresa
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8 * pag.u
                    model: pag.esiti.prese && pag.esiti.prese.ok ? pag.esiti.prese.prese : []
                    delegate: Rectangle {
                        required property var modelData
                        width: listaPrese.width
                        height: 84 * pag.u
                        radius: 14 * pag.u
                        color: pag.imp.batt_presa === modelData.id ? pag.tema.carta : "transparent"
                        border.color: pag.tema.tenue
                        border.width: 1
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 24 * pag.u
                            anchors.rightMargin: 24 * pag.u
                            Text { text: parent.parent.modelData.nome; color: pag.tema.testo; font.pixelSize: 32 * pag.u; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: parent.parent.modelData.id + " · " + parent.parent.modelData.stato; color: pag.tema.tenue; font.pixelSize: 24 * pag.u }
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: { backend.impostaPresa(parent.modelData.id); pag.sceltaPresa = false }
                        }
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !pag.sceltaPresa
                    text: "Consiglio: nell'app della presa imposta «ripristina stato precedente» al ritorno della corrente, "
                          + "e tieni il tablet in un punto ventilato: il calore fa gonfiare la batteria quanto la carica al 100%."
                }
                Item { Layout.fillHeight: true; visible: !pag.sceltaPresa }
            }

            // ============================================ CASA (Home Assistant)
            ColumnLayout {
                spacing: 16 * pag.u
                Titolo { tema: pag.tema; u: pag.u; text: "Home Assistant" }
                Nota {
                    tema: pag.tema; u: pag.u
                    color: pag.imp.ha_url ? pag.tema.testo : pag.tema.tenue
                    text: pag.imp.ha_url ? "Server: " + pag.imp.ha_url + "   ·   token " + (pag.imp.ha_token ? "impostato" : "MANCANTE")
                                         : "Non configurato. Imposta indirizzo, token ed entità dalla scheda «Da PC»."
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    text: "Evento prima della sveglia: " + (pag.imp.ha_anticipo > 0 ? pag.imp.ha_anticipo + " minuti prima" : "disattivato")
                          + ".  La sveglia invia a Home Assistant l'evento «comodino_sveglia» con azione pre / suona / rimanda / spenta: usalo nelle automazioni (es. luci che si accendono piano)."
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    text: pag.imp.telefono
                          ? "📱 Sveglia dal telefono attiva: cambiala da Home Assistant (anche fuori casa). Il Comodino pubblica anche sensor.comodino_prossima_sveglia."
                          : "📱 Sveglia dal telefono: crea in Home Assistant un helper «Data e/o ora» (e un interruttore) e inseriscili da «Da PC»."
                }
                Titolo { tema: pag.tema; u: pag.u; text: "Entità"; Layout.topMargin: 16 * pag.u; visible: backend.haEntita.length > 0 }
                ListView {
                    id: ents
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8 * pag.u
                    model: backend.haEntita
                    delegate: Rectangle {
                        required property var modelData
                        width: ents.width
                        height: 96 * pag.u
                        radius: 14 * pag.u
                        color: "transparent"
                        border.color: pag.tema.tenue
                        border.width: 1
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 24 * pag.u
                            anchors.rightMargin: 12 * pag.u
                            Text {
                                text: parent.parent.modelData.nome
                                color: pag.tema.testo
                                font.pixelSize: 32 * pag.u
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: parent.parent.modelData.stato + (parent.parent.modelData.unita ? " " + parent.parent.modelData.unita : "")
                                color: pag.tema.tenue
                                font.pixelSize: 30 * pag.u
                            }
                            BigButton {
                                tema: pag.tema; u: pag.u
                                visible: parent.parent.modelData.attivabile
                                implicitHeight: 76 * pag.u
                                text: parent.parent.modelData.stato === "on" ? "Spegni" : "Accendi"
                                onClicked: backend.haToggle(parent.parent.modelData.id)
                            }
                        }
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: backend.haEntita.length === 0 && !!pag.imp.ha_url
                    text: "Nessuna entità da mostrare: aggiungile dalla scheda «Da PC»."
                }
            }

            // ============================================ SERVER (Proxmox)
            ColumnLayout {
                id: tabSrv
                spacing: 14 * pag.u
                readonly property var sv: backend.server
                Titolo { tema: pag.tema; u: pag.u; text: "Server Proxmox" }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !tabSrv.sv.configurato
                    text: "Non configurato. Crea in Proxmox un token in sola lettura (ruolo PVEAuditor) e inserisci indirizzo, token ID e segreto da «Da PC»."
                }
                // primo collegamento: conferma del certificato
                ColumnLayout {
                    visible: !!tabSrv.sv.impronta_nuova
                    spacing: 10 * pag.u
                    Nota {
                        tema: pag.tema; u: pag.u
                        color: pag.tema.testo
                        text: "Il server presenta questo certificato. Confrontalo con quello in Proxmox (nodo → Sistema → Certificati → Impronta SHA-256) e conferma solo se coincide:"
                    }
                    Text {
                        Layout.fillWidth: true
                        text: tabSrv.sv.impronta_nuova || ""
                        wrapMode: Text.WrapAnywhere
                        color: pag.tema.accento
                        font.family: "DejaVu Sans Mono"
                        font.pixelSize: 24 * pag.u
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        primary: true
                        text: "🔒  Coincide: fidati di questo certificato"
                        onClicked: { pag.azzera("certificato"); backend.fidatiCertificato() }
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: tabSrv.sv.configurato && !tabSrv.sv.ok && !tabSrv.sv.impronta_nuova
                    color: "#f85149"
                    text: "⚠️ " + (tabSrv.sv.errore || "")
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: (tabSrv.sv.avvisi || []).length > 0
                    color: "#f85149"
                    text: "VM che si sono fermate: " + (tabSrv.sv.avvisi || []).join(", ")
                }
                Repeater {   // nodi
                    model: tabSrv.sv.ok ? tabSrv.sv.nodi : []
                    delegate: Text {
                        required property var modelData
                        text: (modelData.attivo ? "🟢 " : "🔴 ") + modelData.nome + "   CPU " + modelData.cpu + "%   RAM " + modelData.ram + "   acceso da " + modelData.uptime
                        color: pag.tema.testo
                        font.pixelSize: 30 * pag.u
                    }
                }
                ListView {
                    id: listaVm
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 6 * pag.u
                    model: tabSrv.sv.ok ? tabSrv.sv.vm : []
                    delegate: Rectangle {
                        required property var modelData
                        width: listaVm.width
                        height: 74 * pag.u
                        radius: 12 * pag.u
                        color: "transparent"
                        border.color: pag.tema.tenue
                        border.width: 1
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 20 * pag.u
                            anchors.rightMargin: 20 * pag.u
                            spacing: 18 * pag.u
                            Text { text: parent.parent.modelData.attiva ? "🟢" : "⚪"; font.pixelSize: 28 * pag.u }
                            Text {
                                text: parent.parent.modelData.id + "  " + parent.parent.modelData.nome
                                color: pag.tema.testo
                                font.pixelSize: 30 * pag.u
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text { text: parent.parent.modelData.tipo; color: pag.tema.tenue; font.pixelSize: 24 * pag.u }
                            Text {
                                visible: parent.parent.modelData.attiva
                                text: "CPU " + parent.parent.modelData.cpu + "%   " + parent.parent.modelData.ram + "   " + parent.parent.modelData.uptime
                                color: pag.tema.tenue
                                font.pixelSize: 24 * pag.u
                            }
                        }
                    }
                }
            }

            // ============================================ DA PC
            ColumnLayout {
                spacing: 20 * pag.u
                readonly property var w: backend.webStato
                Titolo { tema: pag.tema; u: pag.u; text: "Configura da PC o telefono" }
                Nota {
                    tema: pag.tema; u: pag.u
                    text: "Per inserire i link dei calendari Google e il token di Home Assistant senza digitarli sul tablet. "
                          + "Si apre una pagina sulla rete di casa, protetta da PIN, che si chiude da sola dopo qualche minuto."
                }
                BigButton {
                    tema: pag.tema; u: pag.u
                    primary: !parent.w.attivo
                    text: parent.w.attivo ? "Disattiva" : "Attiva configurazione da browser"
                    onClicked: backend.webAttiva(!parent.w.attivo)
                }
                ColumnLayout {
                    visible: !!parent.w.attivo
                    spacing: 12 * pag.u
                    Layout.topMargin: 20 * pag.u
                    Nota { tema: pag.tema; u: pag.u; text: "1.  Dal PC o dal telefono apri:" }
                    Text { text: parent.parent.w.url || ""; color: pag.tema.accento; font.pixelSize: 58 * pag.u; font.weight: Font.DemiBold }
                    Nota { tema: pag.tema; u: pag.u; text: "2.  Inserisci il PIN:"; Layout.topMargin: 16 * pag.u }
                    Text { text: parent.parent.w.pin || ""; color: pag.tema.testo; font.pixelSize: 120 * pag.u; font.letterSpacing: 16 * pag.u }
                    Nota { tema: pag.tema; u: pag.u; text: "Si disattiva da sola alle " + (parent.parent.w.scade || "") + "." }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !!pag.esiti.web && !pag.esiti.web.ok
                    color: "#f85149"
                    text: pag.esiti.web ? (pag.esiti.web.errore || "") : ""
                }
                Item { Layout.fillHeight: true }
            }

            // ============================================ AGGIORNAMENTI
            ColumnLayout {
                id: tabOta
                spacing: 18 * pag.u
                readonly property var o: backend.otaStato
                Titolo { tema: pag.tema; u: pag.u; text: "Aggiornamenti" }
                Nota {
                    tema: pag.tema; u: pag.u
                    color: pag.tema.testo
                    text: "Versione installata: " + tabOta.o.versione
                          + (tabOta.o.da_aggiornamento ? "  (aggiornamento)" : "  (dalla ISO)")
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    text: tabOta.o.repo ? "Da GitHub: " + tabOta.o.repo
                                        : "Repository non impostato: inseriscilo dalla scheda «Da PC»."
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !tabOta.o.chiave
                    color: "#f85149"
                    text: "⚠️ Manca la chiave pubblica (/etc/comodino/ota.pub): senza, nessun aggiornamento viene accettato."
                }
                RowLayout {
                    spacing: 18 * pag.u
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: "🔍  Controlla"
                        opacity: tabOta.o.occupato || !tabOta.o.repo ? 0.4 : 1
                        onClicked: if (!tabOta.o.occupato && tabOta.o.repo) backend.otaControlla()
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        visible: !!tabOta.o.nuova
                        primary: true
                        text: "⬇️  Installa " + tabOta.o.nuova
                        opacity: tabOta.o.occupato ? 0.4 : 1
                        onClicked: if (!tabOta.o.occupato) backend.otaInstalla()
                    }
                    BigButton {
                        tema: pag.tema; u: pag.u
                        visible: !!tabOta.o.precedente
                        text: "↩️  Torna a " + tabOta.o.precedente
                        opacity: tabOta.o.occupato ? 0.4 : 1
                        onClicked: if (!tabOta.o.occupato) backend.otaRipristina()
                    }
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !!tabOta.o.stato
                    color: pag.tema.testo
                    text: tabOta.o.stato
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !!tabOta.o.errore
                    color: "#f85149"
                    text: "⚠️ " + tabOta.o.errore
                }
                Nota {
                    tema: pag.tema; u: pag.u
                    visible: !!tabOta.o.note
                    maximumLineCount: 8
                    elide: Text.ElideRight
                    text: "Novità " + tabOta.o.nuova + (tabOta.o.data ? " (" + tabOta.o.data + ")" : "") + ":\n" + tabOta.o.note
                }
                RowLayout {
                    Layout.topMargin: 10 * pag.u
                    spacing: 18 * pag.u
                    BigButton {
                        tema: pag.tema; u: pag.u
                        text: tabOta.o.automatico ? "✓ Automatici di notte" : "Automatici spenti"
                        primary: tabOta.o.automatico
                        onClicked: backend.otaAutomatico(!tabOta.o.automatico)
                    }
                    Nota {
                        tema: pag.tema; u: pag.u
                        text: "Tra le 3 e le 5, mai nell'ora prima di una sveglia. Ogni pacchetto deve essere firmato con la tua chiave; "
                              + "se la nuova versione non parte, si torna da soli alla precedente."
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
