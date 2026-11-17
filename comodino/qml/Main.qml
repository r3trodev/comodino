import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Temi.js" as Temi

ApplicationWindow {
    id: win
    visible: true
    title: "Comodino"
    width: modalitaDev ? 1280 : Screen.width
    height: modalitaDev ? 800 : Screen.height
    visibility: modalitaDev ? Window.Windowed : Window.FullScreen
    color: temaApp.sfondo

    // Scala: il layout è disegnato per 1920x1200 (Chuwi Hi10 Pro in orizzontale)
    readonly property real u: Math.min(schermo.width / 1920, schermo.height / 1200)
    readonly property bool notte: backend.notte
    readonly property bool stazione: backend.impostazioni.layout === "stazione" && !notte
    property date adesso: new Date()

    QtObject {
        id: temaApp
        readonly property var giorno: Temi.giorno(backend.impostazioni.tema)
        readonly property var notte: Temi.notte(backend.impostazioni.tema, backend.impostazioni.notte_stile)
        readonly property var c: win.notte ? notte : giorno
        property color sfondo: c.sfondo
        property color carta: c.carta
        property color testo: c.testo
        property color tenue: c.tenue
        property color accento: c.accento
        Behavior on sfondo { ColorAnimation { duration: 1200 } }
        Behavior on carta { ColorAnimation { duration: 1200 } }
        Behavior on testo { ColorAnimation { duration: 1200 } }
        Behavior on tenue { ColorAnimation { duration: 1200 } }
        Behavior on accento { ColorAnimation { duration: 1200 } }
    }

    Timer {
        interval: 1000; running: true; repeat: true
        onTriggered: win.adesso = new Date()
    }

    function pad(n) { return (n < 10 ? "0" : "") + n }
    function maiuscola(s) { return s.length ? s.charAt(0).toUpperCase() + s.slice(1) : s }
    function giorniTesto(g) {
        if (!g || g.length === 0) return "nessun giorno"
        var k = g.slice().sort().join(",")
        if (k === "0,1,2,3,4") return "Lun–Ven"
        if (k === "5,6") return "Weekend"
        if (k === "0,1,2,3,4,5,6") return "Tutti i giorni"
        var nomi = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
        return g.slice().sort().map(function (i) { return nomi[i] }).join(" ")
    }
    function testoSveglia() {
        var s = backend.sveglia
        if (!s.connessa) return "⚠️  Servizio sveglia non attivo"
        if (!s.prossima) return "⏰  Nessuna sveglia attiva"
        var p = new Date(s.prossima)
        var oggi = new Date()
        var domani = new Date(oggi.getFullYear(), oggi.getMonth(), oggi.getDate() + 1)
        var nomi = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"]
        var quando = p.toDateString() === oggi.toDateString() ? ""
                   : p.toDateString() === domani.toDateString() ? "domani " : nomi[p.getDay()] + " "
        var icona = s.prossima_nome === "Pisolino" ? "😴" : "⏰"
        return icona + "  " + quando + Qt.formatTime(p, "HH:mm") + (s.prossima_nome ? "   ·   " + s.prossima_nome : "")
    }

    // Avvisi importanti: allerte meteo e VM ferme (visibili anche di notte)
    readonly property var avvisi: {
        var out = []
        var a = backend.allerte
        for (var i = 0; i < a.length; i++)
            out.push({ testo: "⚠️ " + a[i].testo + (a[i].alle ? " (fino a " + a[i].alle + ")" : ""), colore: a[i].colore })
        var v = backend.server.avvisi || []
        for (var j = 0; j < v.length; j++)
            out.push({ testo: "🖧 VM ferma: " + v[j], colore: "#f85149" })
        return out
    }

    // Agenda: da lista Python a ListModel (serve per le sezioni per giorno)
    ListModel { id: agendaModel }
    function riempiAgenda() {
        agendaModel.clear()
        var rows = backend.agenda
        for (var i = 0; i < rows.length; i++) agendaModel.append(rows[i])
    }
    Connections {
        target: backend
        function onAgendaChanged() { win.riempiAgenda() }
        function onSvegliaChanged() { if (backend.sveglia.suona) { dialogSveglia.close(); impostazioni.chiudi() } }
    }
    Component.onCompleted: riempiAgenda()

    // Tutto il contenuto sta in questo Item ruotato: la rotazione la fa Qt,
    // quindi anche touch, dialoghi e tastiera ruotano in modo coerente.
    Item {
        id: schermo
        readonly property int rot: backend.rotazione
        readonly property bool scambia: rot === 90 || rot === 270
        anchors.centerIn: parent
        width: scambia ? parent.height : parent.width
        height: scambia ? parent.width : parent.height
        rotation: rot

        // Layout "Stazione" (di notte si torna sempre alla vista minima del classico)
        LayoutStazione {
            anchors.fill: parent
            anchors.margins: 36 * win.u
            visible: win.stazione
            tema: temaApp; u: win.u
            adesso: win.adesso
            testoSveglia: win.testoSveglia()
            avvisi: win.avvisi
            onApriSveglia: dialogSveglia.apri()
        }

        RowLayout {
            visible: !win.stazione
            anchors.fill: parent
            anchors.margins: 44 * win.u
            spacing: 44 * win.u

            // ------------------------------------------------ orologio
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1
                spacing: 10 * win.u

                Item { Layout.fillHeight: true }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Qt.formatTime(win.adesso, "HH:mm")
                    color: temaApp.testo
                    font.pixelSize: (win.notte ? 360 : 290) * win.u
                    font.weight: Font.Light
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: win.maiuscola(win.adesso.toLocaleDateString(Qt.locale("it_IT"), "dddd d MMMM"))
                    color: temaApp.tenue
                    font.pixelSize: 58 * win.u
                }
                Item { Layout.preferredHeight: 36 * win.u }
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: chipText.implicitWidth + 70 * win.u
                    implicitHeight: 100 * win.u
                    radius: height / 2
                    color: temaApp.carta
                    border.width: 2
                    border.color: backend.sveglia.attiva ? temaApp.accento : temaApp.tenue
                    Text {
                        id: chipText
                        anchors.centerIn: parent
                        text: win.testoSveglia()
                        color: temaApp.testo
                        font.pixelSize: 42 * win.u
                    }
                    MouseArea { anchors.fill: parent; onClicked: dialogSveglia.apri() }
                }
                Column {   // avvisi: allerte meteo e VM ferme
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 22 * win.u
                spacing: 10 * win.u
                visible: win.avvisi.length > 0
                Repeater {
                    model: win.avvisi
                    delegate: Rectangle {
                        required property var modelData
                        width: avvTxt.implicitWidth + 40 * win.u
                        height: 64 * win.u
                        radius: 14 * win.u
                        color: temaApp.carta
                        border.width: 2
                        border.color: modelData.colore
                        Text {
                            id: avvTxt
                            anchors.centerIn: parent
                            text: parent.modelData.testo
                            color: win.notte ? temaApp.testo : parent.modelData.colore
                            font.pixelSize: 26 * win.u
                        }
                    }
                }
            }
            Flow {   // entità di Home Assistant (tocca per accendere/spegnere)
                Layout.fillWidth: true
                Layout.topMargin: 30 * win.u
                Layout.leftMargin: 20 * win.u
                Layout.rightMargin: 20 * win.u
                visible: !win.notte && backend.haEntita.length > 0
                spacing: 14 * win.u
                Repeater {
                    model: backend.haEntita
                    delegate: Rectangle {
                        required property var modelData
                        readonly property bool acceso: modelData.stato === "on"
                        implicitWidth: chipHa.implicitWidth + 44 * win.u
                        implicitHeight: 72 * win.u
                        radius: height / 2
                        color: acceso ? Qt.rgba(temaApp.accento.r, temaApp.accento.g, temaApp.accento.b, 0.22) : temaApp.carta
                        border.width: 2
                        border.color: acceso ? temaApp.accento : temaApp.tenue
                        Text {
                            id: chipHa
                            anchors.centerIn: parent
                            color: temaApp.testo
                            font.pixelSize: 28 * win.u
                            text: {
                                var m = parent.modelData
                                var v = m.stato === "on" ? "acceso" : (m.stato === "off" ? "spento" : m.stato + (m.unita ? " " + m.unita : ""))
                                return m.nome + "  ·  " + v
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: parent.modelData.attivabile
                            onClicked: backend.haToggle(parent.modelData.id)
                        }
                    }
                }
            }
            Text {   // di notte: riassunto minimo al posto dei pannelli
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 30 * win.u
                    visible: win.notte && backend.meteo.temp !== undefined
                    text: (backend.meteo.icona || "") + "  " + backend.meteo.temp + "°"
                    color: temaApp.tenue
                    font.pixelSize: 48 * win.u
                }
                Item { Layout.fillHeight: true }
            }

            // ------------------------------------------------ meteo + agenda
            ColumnLayout {
                visible: !win.notte
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1
                spacing: 26 * win.u

                Rectangle {
                    id: cardMeteo
                    readonly property var m: backend.meteo
                    readonly property int nOre: (m.ore || []).length
                    readonly property int nGiorni: (m.giorni || []).length
                    Layout.fillWidth: true
                    Layout.preferredHeight: 680 * win.u
                    radius: 26 * win.u
                    color: temaApp.carta

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 30 * win.u
                        spacing: 16 * win.u

                        // ---- adesso
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 26 * win.u
                            IconaMeteo { tema: temaApp; dim: 150 * win.u; testo: cardMeteo.m.icona || "⏳" }
                            ColumnLayout {
                                spacing: 0
                                Text {
                                    text: cardMeteo.m.temp !== undefined ? cardMeteo.m.temp + "°" : "--°"
                                    color: temaApp.testo
                                    font.pixelSize: 112 * win.u
                                }
                                Text {
                                    text: cardMeteo.m.descrizione || "Caricamento meteo…"
                                    color: temaApp.tenue
                                    font.pixelSize: 34 * win.u
                                }
                                Text {
                                    visible: !!cardMeteo.m.pioggia_imminente
                                    text: "🌧  " + (cardMeteo.m.pioggia_imminente || "")
                                    color: temaApp.accento
                                    font.pixelSize: 28 * win.u
                                    font.weight: Font.DemiBold
                                }
                            }
                            Item { Layout.fillWidth: true }
                            ColumnLayout {
                                spacing: 6 * win.u
                                Text { Layout.alignment: Qt.AlignRight; text: backend.citta; color: temaApp.testo; font.pixelSize: 36 * win.u; font.weight: Font.DemiBold }
                                Text { Layout.alignment: Qt.AlignRight; visible: cardMeteo.m.temp !== undefined; color: temaApp.tenue; font.pixelSize: 28 * win.u
                                       text: "Percepita " + cardMeteo.m.percepita + "° · Umidità " + cardMeteo.m.umidita + "%" }
                                Text { Layout.alignment: Qt.AlignRight; visible: cardMeteo.m.temp !== undefined; color: temaApp.tenue; font.pixelSize: 28 * win.u
                                       text: "Vento " + cardMeteo.m.vento + " km/h" }
                                Text { Layout.alignment: Qt.AlignRight; visible: !!cardMeteo.m.alba; color: temaApp.tenue; font.pixelSize: 28 * win.u
                                       text: "🌅 " + cardMeteo.m.alba + "   🌇 " + cardMeteo.m.tramonto
                                             + (cardMeteo.m.luna ? "   " + cardMeteo.m.luna.icona : "") }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: temaApp.tenue; opacity: 0.4 }

                        // ---- prossime ore: celle tutte larghe uguali
                        Row {
                            id: rigaOre
                            Layout.fillWidth: true
                            Layout.preferredHeight: 196 * win.u
                            Repeater {
                                model: cardMeteo.m.ore || []
                                delegate: Column {
                                    required property var modelData
                                    width: rigaOre.width / Math.max(1, cardMeteo.nOre)
                                    spacing: 6 * win.u
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: parent.modelData.ora
                                        color: temaApp.tenue
                                        font.pixelSize: 27 * win.u
                                    }
                                    IconaMeteo {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        tema: temaApp
                                        dim: 74 * win.u
                                        testo: parent.modelData.icona
                                    }
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: parent.modelData.temp + "°"
                                        color: temaApp.testo
                                        font.pixelSize: 34 * win.u
                                    }
                                    Text {   // altezza riservata anche senza pioggia: righe allineate
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        height: 28 * win.u
                                        text: parent.modelData.pioggia > 0 ? "💧" + parent.modelData.pioggia + "%" : ""
                                        color: temaApp.accento
                                        font.pixelSize: 22 * win.u
                                    }
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: temaApp.tenue; opacity: 0.4 }

                        // ---- prossimi giorni: nome, icona, max / min, uno sotto l'altro
                        Row {
                            id: rigaGiorni
                            Layout.fillWidth: true
                            Layout.preferredHeight: 176 * win.u
                            Repeater {
                                model: cardMeteo.m.giorni || []
                                delegate: Column {
                                    required property var modelData
                                    width: rigaGiorni.width / Math.max(1, cardMeteo.nGiorni)
                                    spacing: 6 * win.u
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: parent.modelData.nome
                                        color: temaApp.testo
                                        font.pixelSize: 28 * win.u
                                        font.weight: Font.DemiBold
                                    }
                                    IconaMeteo {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        tema: temaApp
                                        dim: 74 * win.u
                                        testo: parent.modelData.icona
                                    }
                                    Row {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        spacing: 10 * win.u
                                        Text { text: parent.parent.modelData.max + "°"; color: temaApp.testo; font.pixelSize: 30 * win.u }
                                        Text { text: parent.parent.modelData.min + "°"; color: temaApp.tenue; font.pixelSize: 30 * win.u }
                                    }
                                }
                            }
                        }
                        Item { Layout.fillHeight: true }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 26 * win.u
                    color: temaApp.carta

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 30 * win.u
                        spacing: 10 * win.u

                        RowLayout {
                            Text { text: "📅  Agenda"; color: temaApp.testo; font.pixelSize: 36 * win.u; font.weight: Font.Bold }
                            Item { Layout.fillWidth: true }
                            Text {
                            text: backend.errore
                            color: "#d29922"
                            font.pixelSize: 22 * win.u
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignRight
                            Layout.maximumWidth: 560 * win.u
                        }
                        }

                        ListView {
                            id: lista
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            spacing: 10 * win.u
                            model: agendaModel
                            section.property: "giorno"
                            section.delegate: Text {
                                required property string section
                                text: section
                                color: temaApp.accento
                                font.pixelSize: 30 * win.u
                                font.weight: Font.Bold
                                topPadding: 14 * win.u
                                bottomPadding: 4 * win.u
                            }
                            delegate: RowLayout {
                                required property string ora
                                required property string titolo
                                required property string luogo
                                required property bool passato
                                width: lista.width
                                opacity: passato ? 0.4 : 1.0
                                spacing: 20 * win.u
                                Text {
                                    Layout.preferredWidth: 230 * win.u
                                    Layout.alignment: Qt.AlignTop
                                    text: parent.ora
                                    color: temaApp.tenue
                                    font.pixelSize: 30 * win.u
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Text {
                                        Layout.fillWidth: true
                                        text: parent.parent.titolo
                                        color: temaApp.testo
                                        font.pixelSize: 32 * win.u
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        visible: parent.parent.luogo !== ""
                                        text: "📍 " + parent.parent.luogo
                                        color: temaApp.tenue
                                        font.pixelSize: 23 * win.u
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }
                        Text {
                            visible: lista.count === 0
                            text: "Nessun impegno nei prossimi giorni"
                            color: temaApp.tenue
                            font.pixelSize: 30 * win.u
                        }
                    }
                }
            }
        }

        // Di notte un tocco ovunque riaccende lo schermo (l'evento passa comunque sotto)
        MouseArea {
            anchors.fill: parent
            z: 100
            onPressed: function (mouse) { backend.tocco(); mouse.accepted = false }
        }

        AlarmDialog { id: dialogSveglia; anchors.fill: parent; z: 500; tema: temaApp; u: win.u }

        Alba {
            anchors.fill: parent
            z: 900
            u: win.u
            adesso: win.adesso
        }

        RingingOverlay {
            anchors.fill: parent
            z: 1000
            tema: temaApp; u: win.u
            adesso: win.adesso
        }

        // Indicatore batteria (in alto a sinistra)
        Text {
            z: 50
            readonly property var b: backend.batteria
            visible: !!b.presente && !win.stazione
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.margins: 24 * win.u
            text: (b.alimentato ? "⚡ " : "🔋 ") + b.percentuale + "%"
            color: b.avviso ? "#f85149" : temaApp.tenue
            opacity: win.notte && !b.avviso ? 0.5 : 0.9
            font.pixelSize: 30 * win.u
        }

        // Avviso batteria bassa: visibile anche di notte
        Rectangle {
            z: 60
            readonly property var b: backend.batteria
            visible: !!b.avviso
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.topMargin: 16 * win.u
            width: avvisoTxt.implicitWidth + 60 * win.u
            height: 80 * win.u
            radius: 16 * win.u
            color: "#3d0d0d"
            border.color: "#f85149"
            border.width: 2
            Text {
                id: avvisoTxt
                anchors.centerIn: parent
                color: "#ffb3ad"
                font.pixelSize: 30 * win.u
                text: "⚠️  Batteria al " + parent.b.percentuale + "% e il tablet non si sta caricando"
            }
        }

        // Pulsante impostazioni (in basso a sinistra)
        Rectangle {
            z: 50
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.margins: 18 * win.u
            width: 96 * win.u
            height: width
            radius: width / 2
            color: "transparent"
            opacity: win.notte ? 0.25 : 0.7
            Text { anchors.centerIn: parent; text: "⚙️"; font.pixelSize: 54 * win.u }
            MouseArea { anchors.fill: parent; onClicked: impostazioni.apri() }
        }

        SettingsPage {
            id: impostazioni
            anchors.fill: parent
            z: 800
            tema: temaApp; u: win.u
        }

        // Tastiera virtuale (solo sul tablet)
        Loader {
            anchors.fill: parent
            z: 3000
            active: !modalitaDev
            source: "Tastiera.qml"
        }
    }
}
