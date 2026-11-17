import QtQuick
import QtQuick.VirtualKeyboard

// Tastiera virtuale: compare quando si tocca un campo di testo.
// È caricata con un Loader: se il modulo manca (es. sul PC) il resto funziona lo stesso.
Item {
    id: root
    InputPanel {
        id: ip
        width: Math.min(root.width, root.height * 1.35)
        x: (root.width - width) / 2
        y: ip.active ? root.height - ip.height : root.height
        Behavior on y { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
    }
}
