import QtQuick
import QtQuick.Layouts

// Layout "Stazione": tre colonne (ora e clima, dettagli, settimana) e una barra in basso.
// Usa i colori del tema scelto; con il tema "E-ink" ha l'aspetto di un display a inchiostro.
Item {
    id: st
    property var tema
    property real u: 1
    property date adesso: new Date()
    property string testoSveglia: ""
    property var avvisi: []
    signal apriSveglia()
    signal apriServer()
    signal apriImpostazioni()
    signal apriAvvisi()

    readonly property var m: backend.meteo
    readonly property var aria: m.aria || ({})
    readonly property var cl: backend.clima
    readonly property string mono: "DejaVu Sans Mono"
    readonly property string lcd: "DSEG7 Classic"
    readonly property string emoji: "Noto Color Emoji"     // icone sempre a colori

    function nd(v, suff) { return (v === undefined || v === null) ? "—" : v + (suff || "") }
    function maiuscola(s) { return s.length ? s.charAt(0).toUpperCase() + s.slice(1) : s }
    function comfort(t, h) {
        if (t === undefined || t === null) return ""
        if (t < 18) return "🥶 freddo"
        if (t > 26) return "🥵 caldo"
        if (h !== undefined && h !== null && h < 35) return "🌵 secco"
        if (h !== undefined && h !== null && h > 65) return "💧 umido"
        return "🙂 ok"
    }
    function prossimoEvento() {
        var a = backend.agenda
        for (var i = 0; i < a.length; i++)
            if (!a[i].passato) return a[i].giorno + " " + (a[i].ora === "Tutto il giorno" ? "" : a[i].ora + " ") + a[i].titolo
        return "Nessun impegno in arrivo"
    }

    readonly property color bordo: Qt.rgba(tema.tenue.r, tema.tenue.g, tema.tenue.b, 0.45)
    readonly property color linea: Qt.rgba(tema.tenue.r, tema.tenue.g, tema.tenue.b, 0.35)

    ColumnLayout {
        anchors.fill: parent
        spacing: 18 * st.u

        // ------------------------------------------------ intestazione
        RowLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: st.width
            spacing: 26 * st.u
            Text {
                text: "📍 " + backend.citta + "   ⟳ " + (st.m.aggiornato || "--:--")
                color: st.tema.testo
                font.family: st.mono
                font.pixelSize: 32 * st.u
            }
            Item { Layout.fillWidth: true }
            Text {
                readonly property var av: st.avvisi
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                visible: av.length > 0 || !!st.m.pioggia_imminente
                text: av.length ? av[0].testo + (av.length > 1 ? "  (+" + (av.length - 1) + ")" : "")
                                : "🌧 " + st.m.pioggia_imminente
                color: av.length ? av[0].colore : st.tema.accento
                font.family: st.mono
                font.pixelSize: 28 * st.u
                font.weight: Font.DemiBold
                MouseArea {   // tocca per vederli tutti
                    anchors.fill: parent
                    anchors.margins: -16 * st.u
                    onClicked: st.apriAvvisi()
                }
            }
            Item { Layout.fillWidth: true }
            Text {
                readonly property var b: backend.batteria
                visible: !!b.presente
                text: (b.alimentato ? "⚡ " : "🔋 ") + b.percentuale + "%"
                color: b.avviso ? "#f85149" : st.tema.tenue
                font.family: st.mono
                font.pixelSize: 30 * st.u
            }
        }

        RowLayout {
            id: colonne
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: st.width
            spacing: 22 * st.u
            readonly property real utile: st.width - 2 * spacing

            // ============================================ colonna 1: ora e clima
            Rectangle {   // pannello
                color: st.tema.carta
                radius: 18 * st.u
                border.width: 2
                border.color: st.bordo
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                Layout.minimumWidth: colonne.utile * 0.34
                Layout.maximumWidth: colonne.utile * 0.34
                Layout.preferredWidth: colonne.utile * 0.34
                clip: true      // il contenuto non deve mai allargare la colonna

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 26 * st.u
                    spacing: 12 * st.u

                    Text {
                        text: st.maiuscola(st.adesso.toLocaleDateString(Qt.locale("it_IT"), "ddd d MMMM yyyy"))
                        color: st.tema.tenue
                        font.family: st.mono
                        font.pixelSize: 30 * st.u
                    }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: Qt.formatTime(st.adesso, "HH:mm")
                        color: st.tema.testo
                        font.family: st.lcd
                        Layout.minimumWidth: 0
                        font.pixelSize: 150 * st.u
                        fontSizeMode: Text.HorizontalFit     // non esce mai dal pannello
                        minimumPixelSize: 60 * st.u
                    }
                    RowLayout {
                        spacing: 20 * st.u
                        IconaMeteo { tema: st.tema; dim: 120 * st.u; testo: st.m.icona || "⏳" }
                        ColumnLayout {
                            spacing: 0
                            Text { text: st.m.descrizione || "…"; color: st.tema.tenue; font.family: st.mono; font.pixelSize: 26 * st.u }
                            Text {
                                text: st.m.giorni && st.m.giorni.length ? st.m.giorni[0].max + "°/" + st.m.giorni[0].min + "°" : "--/--"
                                color: st.tema.testo
                                font.family: st.mono
                                font.pixelSize: 54 * st.u
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 2; color: st.linea }

                    // Fuori / Dentro: la misura del termometro se c'è, altrimenti la previsione
                    Repeater {
                        model: {
                            var e = st.cl.esterno || {}
                            var i = st.cl.interno || {}
                            var misurata = e.temp !== undefined
                            var fuori = {
                                nome: "Fuori",
                                dati: misurata ? { temp: e.temp, umidita: e.umidita !== undefined ? e.umidita : st.m.umidita }
                                               : { temp: st.m.temp_decimale, umidita: st.m.umidita },
                                nota: misurata ? "misurata" : (e.vecchio ? "termometro muto · previsione" : "previsione"),
                                extra: misurata && st.m.temp_decimale !== undefined ? "modello " + st.m.temp_decimale + "°" : "",
                                avviso: ""      // la pila scarica compare tra gli avvisi in alto
                            }
                            var dentro = {
                                nome: "Dentro",
                                dati: i,
                                nota: i.temp !== undefined ? "" : (i.vecchio ? "termometro muto" : "nessun sensore"),
                                extra: st.comfort(i.temp, i.umidita),
                                avviso: ""
                            }
                            return [fuori, dentro]
                        }
                        delegate: ColumnLayout {
                            id: riga
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 0
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 14 * st.u
                                Text {
                                    text: riga.modelData.nome + (riga.modelData.nota ? " · " + riga.modelData.nota : "")
                                    color: st.tema.tenue
                                    font.family: st.mono
                                    font.pixelSize: 28 * st.u
                                }
                                Item { Layout.fillWidth: true }
                                Text {
                                    Layout.rightMargin: 12 * st.u
                                    visible: riga.modelData.extra !== ""
                                    text: riga.modelData.extra
                                    color: st.tema.tenue
                                    font.family: st.mono
                                    font.pixelSize: 26 * st.u
                                }
                            }
                            RowLayout {
                                spacing: 34 * st.u
                                Text {
                                    text: "🌡 " + st.nd(riga.modelData.dati.temp, "°")
                                    color: st.tema.testo
                                    font.family: st.mono
                                    font.pixelSize: 56 * st.u
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: "💧 " + st.nd(riga.modelData.dati.umidita, "%")
                                    color: st.tema.testo
                                    font.family: st.mono
                                    font.pixelSize: 56 * st.u
                                }
                            }
                            Text {
                                visible: riga.modelData.avviso !== ""
                                text: riga.modelData.avviso
                                color: "#f0883e"
                                font.family: st.mono
                                font.pixelSize: 24 * st.u
                            }
                        }
                    }
                    // rischio muffa (serve il termometro dentro)
                    Text {
                        readonly property var mf: backend.muffa
                        visible: !!mf.livello
                        text: !mf.livello ? "" : "🍄 " + st.maiuscola(mf.testo) + " · rugiada " + mf.rugiada + "°"
                        color: mf.livello === "ok" ? st.tema.tenue
                             : (mf.livello === "attenzione" ? st.tema.accento : "#f0883e")
                        font.family: st.mono
                        font.pixelSize: 24 * st.u
                    }

                    // grafico delle ultime 24 ore (riempie lo spazio libero)
                    Grafico24 {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: 6 * st.u
                        Layout.minimumHeight: 60 * st.u
                        tema: st.tema
                        u: st.u
                        punti: backend.storico
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 2; color: st.linea }
                    // alba e tramonto: icona e ora separate, con margine dal bordo del pannello
                    // (la larghezza delle emoji a colori non sempre viene misurata bene)
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14 * st.u
                        Layout.rightMargin: 24 * st.u
                        spacing: 12 * st.u
                        Text { text: "🌅"; font.family: st.emoji; font.pixelSize: 32 * st.u; Layout.preferredWidth: 44 * st.u }
                        Text { text: st.m.alba || "--:--"; color: st.tema.testo; font.family: st.mono; font.pixelSize: 32 * st.u }
                        Item { Layout.fillWidth: true }
                        Text {   // fase lunare al centro: icona e percentuale
                            visible: !!st.m.luna
                            text: st.m.luna ? st.m.luna.icona : ""
                            font.family: st.emoji
                            font.pixelSize: 30 * st.u
                        }
                        Text {
                            visible: !!st.m.luna
                            text: st.m.luna ? st.m.luna.illuminazione + "%" : ""
                            color: st.tema.tenue
                            font.family: st.mono
                            font.pixelSize: 26 * st.u
                        }
                        Item { Layout.fillWidth: true }
                        Text { text: "🌇"; font.family: st.emoji; font.pixelSize: 32 * st.u; Layout.preferredWidth: 44 * st.u }
                        Text { text: st.m.tramonto || "--:--"; color: st.tema.testo; font.family: st.mono; font.pixelSize: 32 * st.u }
                    }
                }
            }

            // ============================================ colonna 2: dettagli
            Rectangle {   // pannello
                color: st.tema.carta
                radius: 18 * st.u
                border.width: 2
                border.color: st.bordo
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                Layout.minimumWidth: colonne.utile * 0.35
                Layout.maximumWidth: colonne.utile * 0.35
                Layout.preferredWidth: colonne.utile * 0.35
                clip: true      // il contenuto non deve mai allargare la colonna

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 26 * st.u
                    spacing: 6 * st.u

                    RowLayout {   // qualità dell'aria
                        Layout.fillWidth: true
                        Repeater {
                            model: [
                                { t: "Aria (AQI)", v: st.nd(st.aria.aqi), s: st.aria.aqi_testo || "" },
                                { t: "PM2.5", v: st.nd(st.aria.pm25), s: "µg/m³" },
                                { t: "Polline", v: st.aria.polline || "—", s: "" }
                            ]
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 0
                                Text { Layout.alignment: Qt.AlignHCenter; text: parent.modelData.t; color: st.tema.tenue; font.family: st.mono; font.pixelSize: 24 * st.u }
                                Text { Layout.alignment: Qt.AlignHCenter; text: parent.modelData.v; color: st.tema.testo; font.family: st.mono; font.pixelSize: 44 * st.u }
                                Text { Layout.alignment: Qt.AlignHCenter; text: parent.modelData.s; color: st.tema.tenue; font.family: st.mono; font.pixelSize: 20 * st.u }
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 2; color: st.linea; Layout.topMargin: 8 * st.u; Layout.bottomMargin: 8 * st.u }

                    Repeater {
                        model: [
                            { i: "🍃", t: "Vento", v: st.nd(st.m.vento, " km/h") },
                            { i: "🧭", t: "Direzione", v: st.m.direzione ? st.m.direzione + " " + st.m.direzione_gradi + "°" : "—" },
                            { i: "☀️", t: "Indice UV", v: st.nd(st.m.uv) },
                            { i: "☔", t: "Pioggia", v: st.nd(st.m.pioggia_mm, " mm") },
                            { i: "👁️", t: "Visibilità", v: st.nd(st.m.visibilita_km, " km") },
                            { i: "📈", t: "Pressione", v: st.nd(st.m.pressione, " hPa") }
                        ]
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 16 * st.u
                            Text { text: parent.modelData.i; font.family: st.emoji; font.pixelSize: 34 * st.u; Layout.preferredWidth: 52 * st.u }
                            Text { text: parent.modelData.t; color: st.tema.tenue; font.family: st.mono; font.pixelSize: 30 * st.u }
                            Item { Layout.fillWidth: true }
                            Text { text: parent.modelData.v; color: st.tema.testo; font.family: st.mono; font.pixelSize: 42 * st.u }
                        }
                    }
                }
            }

            // ============================================ colonna 3: settimana
            Rectangle {   // pannello
                color: st.tema.carta
                radius: 18 * st.u
                border.width: 2
                border.color: st.bordo
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                Layout.minimumWidth: colonne.utile * 0.31
                Layout.maximumWidth: colonne.utile * 0.31
                Layout.preferredWidth: colonne.utile * 0.31
                clip: true      // il contenuto non deve mai allargare la colonna

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 22 * st.u
                    spacing: 0

                    Repeater {
                        model: st.m.settimana || []
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 16 * st.u
                            opacity: modelData.passato ? 0.55 : 1.0
                            IconaMeteo { tema: st.tema; dim: 78 * st.u; testo: parent.modelData.icona }
                            ColumnLayout {
                                spacing: 0
                                Text {
                                    text: parent.parent.modelData.nome
                                    color: st.tema.testo
                                    font.family: st.mono
                                    font.pixelSize: 30 * st.u
                                    font.weight: parent.parent.modelData.nome === "Oggi" ? Font.Bold : Font.Normal
                                }
                                Text {
                                    visible: parent.parent.modelData.pioggia > 0
                                    text: "💧" + parent.parent.modelData.pioggia + "%"
                                    color: st.tema.accento
                                    font.family: st.mono
                                    font.pixelSize: 22 * st.u
                                }
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: parent.modelData.max + "°/" + parent.modelData.min + "°"
                                color: st.tema.testo
                                font.family: st.mono
                                font.pixelSize: 38 * st.u
                            }
                        }
                    }
                    Text {
                        visible: !(st.m.settimana && st.m.settimana.length)
                        text: "Caricamento…"
                        color: st.tema.tenue
                        font.family: st.mono
                        font.pixelSize: 28 * st.u
                    }
                }
            }
        }

        // ------------------------------------------------ barra in basso
        Rectangle {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: st.width
            Layout.preferredHeight: 96 * st.u
            radius: 18 * st.u
            color: st.tema.testo
            clip: true

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8 * st.u
                anchors.rightMargin: 24 * st.u
                spacing: 20 * st.u

                Item {    // impostazioni: grande e centrato sul lato sinistro della barra
                    Layout.preferredWidth: 104 * st.u
                    Layout.fillHeight: true
                    Text {
                        anchors.centerIn: parent
                        text: "⚙️"
                        font.family: st.emoji
                        font.pixelSize: 66 * st.u
                    }
                    MouseArea { anchors.fill: parent; anchors.margins: -8 * st.u; onClicked: st.apriImpostazioni() }
                }
                Rectangle { Layout.preferredWidth: 2; Layout.preferredHeight: 50 * st.u; color: st.tema.sfondo; opacity: 0.4 }

                Text {    // sveglia: tocca per impostarla
                    text: st.testoSveglia
                    color: st.tema.sfondo
                    font.family: st.mono
                    font.pixelSize: 30 * st.u
                    MouseArea { anchors.fill: parent; anchors.margins: -16 * st.u; onClicked: st.apriSveglia() }
                }
                Rectangle { Layout.preferredWidth: 2; Layout.preferredHeight: 50 * st.u; color: st.tema.sfondo; opacity: 0.4 }
                Text {
                    Layout.fillWidth: true
                    text: "📅 " + st.prossimoEvento()
                    color: st.tema.sfondo
                    font.family: st.mono
                    font.pixelSize: 28 * st.u
                    elide: Text.ElideRight
                }
                Rectangle {   // spia del server
                    readonly property var sp: backend.server.spia || null
                    visible: !!sp
                    implicitWidth: spTxt.implicitWidth + 36 * st.u
                    implicitHeight: 62 * st.u
                    radius: height / 2
                    color: "transparent"
                    border.width: 2
                    border.color: !sp ? "transparent" : (sp.livello === "ok" ? st.tema.sfondo
                                  : (sp.livello === "attenzione" ? "#d29922" : "#f85149"))
                    Text {
                        id: spTxt
                        anchors.centerIn: parent
                        text: !parent.sp ? "" : (parent.sp.livello === "ok" ? "✅ " + parent.sp.testo.replace("Server ok · ", "Server ")
                                                                           : "⚠️ " + parent.sp.testo)
                        color: !parent.sp || parent.sp.livello === "ok" ? st.tema.sfondo : (parent.sp.livello === "attenzione" ? "#d29922" : "#f85149")
                        font.family: st.mono
                        font.pixelSize: 24 * st.u
                    }
                    MouseArea { anchors.fill: parent; onClicked: st.apriServer() }
                }
                Repeater {    // entità di Home Assistant (max 3)
                    model: backend.haEntita.slice(0, 3)
                    delegate: Rectangle {
                        required property var modelData
                        readonly property bool acceso: modelData.stato === "on"
                        implicitWidth: haTxt.implicitWidth + 36 * st.u
                        implicitHeight: 62 * st.u
                        radius: height / 2
                        color: acceso ? st.tema.sfondo : "transparent"
                        border.width: 2
                        border.color: st.tema.sfondo
                        Text {
                            id: haTxt
                            anchors.centerIn: parent
                            text: parent.modelData.nome
                            color: parent.acceso ? st.tema.testo : st.tema.sfondo
                            font.family: st.mono
                            font.pixelSize: 24 * st.u
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: parent.modelData.attivabile
                            onClicked: backend.haToggle(parent.modelData.id)
                        }
                    }
                }
            }
        }
    }
}
