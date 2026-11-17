.pragma library

// Temi per il giorno: sfondo, carta (riquadri), testo, tenue (testo secondario), accento.
var TEMI = {
    "notte":   { nome: "Notte",         sfondo: "#0d1117", carta: "#161b22", testo: "#e6edf3", tenue: "#8b949e", accento: "#58a6ff" },
    "ardesia": { nome: "Ardesia",       sfondo: "#1c1d21", carta: "#27292e", testo: "#f2f3f5", tenue: "#9a9ea6", accento: "#e2a03f" },
    "oceano":  { nome: "Oceano",        sfondo: "#0a1a26", carta: "#112738", testo: "#e3f2fd", tenue: "#7fa3bd", accento: "#4fc3f7" },
    "foresta": { nome: "Foresta",       sfondo: "#0e1712", carta: "#16241b", testo: "#e8f5e9", tenue: "#8aa793", accento: "#66bb6a" },
    "tramonto":{ nome: "Tramonto",      sfondo: "#1b1016", carta: "#2a1820", testo: "#fde8ef", tenue: "#b58d9c", accento: "#ff8a65" },
    "lavanda": { nome: "Lavanda",       sfondo: "#15121d", carta: "#211c2c", testo: "#f3e8ff", tenue: "#a497b7", accento: "#b39ddb" },
    "oled":    { nome: "Nero OLED",     sfondo: "#000000", carta: "#0b0b0b", testo: "#ffffff", tenue: "#8a8a8a", accento: "#ffffff" },
    "chiaro":  { nome: "Chiaro",        sfondo: "#f3f4f1", carta: "#ffffff", testo: "#1f2328", tenue: "#5f6871", accento: "#0969da" },
    "sabbia":  { nome: "Sabbia",        sfondo: "#f2ebe0", carta: "#fbf7f0", testo: "#3b3127", tenue: "#857563", accento: "#c2410c" },
    "eink":    { nome: "E-ink",         sfondo: "#dcdcd7", carta: "#e8e8e3", testo: "#2a2a2a", tenue: "#666661", accento: "#2a2a2a" }
}
var ORDINE = ["notte", "ardesia", "oceano", "foresta", "tramonto", "lavanda", "oled", "chiaro", "sabbia", "eink"]

// Colori della modalità notte (schermo al minimo): niente blu, poca luce.
// "giorno" = usa gli stessi colori del tema scelto.
var NOTTE = {
    "rosso":  { nome: "Rosso",  sfondo: "#000000", carta: "#000000", testo: "#9a2323", tenue: "#4d1111", accento: "#9a2323" },
    "ambra":  { nome: "Ambra",  sfondo: "#000000", carta: "#000000", testo: "#a8641a", tenue: "#55320d", accento: "#a8641a" },
    "grigio": { nome: "Grigio", sfondo: "#000000", carta: "#000000", testo: "#6e6e6e", tenue: "#333333", accento: "#6e6e6e" },
    "giorno": { nome: "Come il tema" }
}
var ORDINE_NOTTE = ["rosso", "ambra", "grigio", "giorno"]

function giorno(id) { return TEMI[id] || TEMI["notte"] }

function notte(idTema, idNotte) {
    var n = NOTTE[idNotte] || NOTTE["rosso"]
    return n.sfondo ? n : giorno(idTema)
}
