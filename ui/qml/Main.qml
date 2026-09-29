// Màn hình điều khiển cảm ứng.
//
// Thiết kế cho ngón tay, không cho chuột: vùng chạm tối thiểu 56px, chữ to, nền
// tối để không chói trong phòng hát. Không có thanh cuộn mảnh, không có menu
// chuột phải, không có gì cần độ chính xác cao hơn một đầu ngón tay.

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    visible: true
    visibility: Window.FullScreen
    title: "KaraokeBooth"
    color: "#0f1115"

    readonly property var player: backend.state.player || ({})
    readonly property var queue: backend.state.queue || ({ items: [], current: null })
    readonly property int tap: 56

    function fmt(seconds) {
        if (!seconds) return "0:00"
        var s = Math.round(seconds)
        return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2)
    }

    // ---------------------------------------------------------------- header

    header: ToolBar {
        height: 72
        background: Rectangle { color: "#191d26" }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            spacing: 16

            Label {
                text: "KaraokeBooth"
                color: "#f2f4f8"
                font.pixelSize: 22
                font.bold: true
            }

            Item { Layout.fillWidth: true }

            Rectangle {
                width: 12; height: 12; radius: 6
                color: backend.connected ? "#4ade80" : "#fb7185"
            }
            Label {
                text: backend.connected ? "Đã kết nối" : "Mất kết nối core"
                color: "#98a1b3"
                font.pixelSize: 15
            }
        }
    }

    // ---------------------------------------------------------------- nội dung

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 16

        // --- Đang hát ---
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 128
            radius: 16
            color: "#191d26"
            border.color: "#3a2e17"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 4

                Label {
                    text: "ĐANG HÁT"
                    color: "#ffb020"
                    font.pixelSize: 13
                    font.letterSpacing: 1.5
                }
                Label {
                    Layout.fillWidth: true
                    text: queue.current ? queue.current.song.title : "Chưa có bài nào"
                    color: "#f2f4f8"
                    font.pixelSize: 26
                    font.bold: true
                    elide: Text.ElideRight
                }
                Label {
                    text: queue.current
                          ? (queue.current.singer || "—") + "  ·  "
                            + fmt(player.position) + " / " + fmt(player.duration)
                          : ""
                    color: "#98a1b3"
                    font.pixelSize: 15
                }
            }
        }

        // --- Điều khiển ---
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Repeater {
                model: [
                    { label: player.state === "playing" ? "Tạm dừng" : "Phát", action: "toggle" },
                    { label: "Hát lại", action: "replay" },
                    { label: "Bài kế", action: "next" }
                ]
                delegate: Button {
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.tap + 8
                    text: modelData.label
                    font.pixelSize: 18
                    font.bold: true
                    enabled: backend.connected
                    onClicked: {
                        if (modelData.action === "toggle") backend.togglePause()
                        else if (modelData.action === "replay") backend.replay()
                        else backend.playNext()
                    }
                    background: Rectangle {
                        radius: 14
                        color: parent.down ? "#2c3446" : "#222836"
                    }
                    contentItem: Text {
                        text: parent.text
                        color: parent.enabled ? "#f2f4f8" : "#5b6474"
                        font: parent.font
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        // --- Đổi tông ---
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            visible: player.capabilities ? player.capabilities.can_pitch : false

            Label {
                text: "Tông"
                color: "#98a1b3"
                font.pixelSize: 17
            }
            Button {
                Layout.preferredWidth: root.tap + 12
                Layout.preferredHeight: root.tap
                text: "−"
                font.pixelSize: 24
                onClicked: backend.setPitch((player.pitch || 0) - 1)
            }
            Label {
                Layout.preferredWidth: 64
                text: (player.pitch > 0 ? "+" : "") + (player.pitch || 0)
                color: "#ffb020"
                font.pixelSize: 22
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Button {
                Layout.preferredWidth: root.tap + 12
                Layout.preferredHeight: root.tap
                text: "+"
                font.pixelSize: 24
                onClicked: backend.setPitch((player.pitch || 0) + 1)
            }
            Item { Layout.fillWidth: true }
            // Bài video pitch-shift cả bản mix nên luôn có artifact — nói thẳng
            // với người vận hành thay vì để họ tưởng máy hỏng.
            Label {
                visible: player.capabilities && player.capabilities.pitch_quality === "dsp"
                text: "Bài video: đổi tông nhiều sẽ hơi rè"
                color: "#5b6474"
                font.pixelSize: 13
            }
        }

        // --- Hàng chờ ---
        Label {
            text: "Hàng chờ (" + (queue.items ? queue.items.length : 0) + ")"
            color: "#98a1b3"
            font.pixelSize: 17
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 10
            model: queue.items || []

            delegate: Rectangle {
                width: ListView.view.width
                height: 76
                radius: 14
                color: "#191d26"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 12
                    spacing: 14

                    Label {
                        text: index + 1
                        color: "#5b6474"
                        font.pixelSize: 19
                        Layout.preferredWidth: 32
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            Layout.fillWidth: true
                            text: modelData.song.title
                            color: "#f2f4f8"
                            font.pixelSize: 18
                            elide: Text.ElideRight
                        }
                        Label {
                            text: (modelData.singer || modelData.song.channel || "")
                                  + (modelData.ready ? "" : "  ·  đang tải")
                            color: "#98a1b3"
                            font.pixelSize: 14
                        }
                    }
                    Button {
                        Layout.preferredWidth: 96
                        Layout.preferredHeight: root.tap
                        text: "Xoá"
                        onClicked: backend.removeItem(modelData.id)
                    }
                }
            }
        }
    }
}
