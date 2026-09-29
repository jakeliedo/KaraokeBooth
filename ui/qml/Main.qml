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
    readonly property int tap: 56          // vùng chạm tối thiểu theo Material/HIG
    readonly property int radius: 14

    function fmt(seconds) {
        if (!seconds) return "0:00"
        var s = Math.round(seconds)
        return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2)
    }

    // ---------------------------------------------------------------- màu sắc
    QtObject {
        id: colors
        readonly property color bg:       "#0f1115"
        readonly property color surface:  "#191d26"
        readonly property color surface2: "#222836"
        readonly property color text:     "#f2f4f8"
        readonly property color muted:    "#98a1b3"
        readonly property color accent:   "#ffb020"
        readonly property color ok:       "#4ade80"
        readonly property color danger:   "#fb7185"
    }

    // ---------------------------------------------------------------- header
    header: ToolBar {
        height: 72
        background: Rectangle { color: colors.surface }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20
            spacing: 16

            Label {
                text: "KaraokeBooth"
                color: colors.text; font.pixelSize: 22; font.bold: true
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                width: 12; height: 12; radius: 6
                color: backend.connected ? colors.ok : colors.danger
            }
            Label {
                text: backend.connected ? "Đã kết nối" : "Mất kết nối core"
                color: colors.muted; font.pixelSize: 15
            }
        }
    }

    // ---------------------------------------------------------------- tabs
    footer: TabBar {
        id: tabBar
        background: Rectangle { color: colors.surface }
        TabButton { text: "Đang phát";  font.pixelSize: 16 }
        TabButton { text: "Tìm bài";    font.pixelSize: 16 }
        TabButton { text: "Hàng chờ";  font.pixelSize: 16 }
        TabButton { text: "Cài đặt";   font.pixelSize: 16 }
    }

    // ---------------------------------------------------------------- nội dung
    StackLayout {
        anchors.fill: parent
        currentIndex: tabBar.currentIndex

        // ====================================================== Tab 0: Đang phát
        Item {
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 16

                // --- Đang hát ---
                Rectangle {
                    Layout.fillWidth: true; implicitHeight: 128
                    radius: root.radius; color: colors.surface
                    border.color: "#3a2e17"

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 18; spacing: 4
                        Label {
                            text: "ĐANG HÁT"; color: colors.accent
                            font.pixelSize: 13; font.letterSpacing: 1.5
                        }
                        Label {
                            Layout.fillWidth: true
                            text: queue.current ? queue.current.song.title : "Chưa có bài nào"
                            color: colors.text; font.pixelSize: 26; font.bold: true
                            elide: Text.ElideRight
                        }
                        Label {
                            text: queue.current
                                  ? (queue.current.singer || "—") + "  ·  "
                                    + fmt(player.position) + " / " + fmt(player.duration)
                                  : ""
                            color: colors.muted; font.pixelSize: 15
                        }
                    }
                }

                // --- Điều khiển phát ---
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Repeater {
                        model: [
                            { label: player.state === "playing" ? "Tạm dừng" : "Phát",
                              action: "toggle" },
                            { label: "Hát lại", action: "replay" },
                            { label: "Bài kế",  action: "next"   }
                        ]
                        delegate: Button {
                            Layout.fillWidth: true; Layout.preferredHeight: root.tap + 8
                            text: modelData.label
                            font.pixelSize: 18; font.bold: true
                            enabled: backend.connected
                            onClicked: {
                                if      (modelData.action === "toggle") backend.togglePause()
                                else if (modelData.action === "replay") backend.replay()
                                else backend.playNext()
                            }
                            background: Rectangle { radius: root.radius
                                color: parent.down ? colors.surface2 : colors.surface }
                            contentItem: Text {
                                text: parent.text; font: parent.font
                                color: parent.enabled ? colors.text : colors.muted
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                // --- Âm lượng ---
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Label { text: "Âm lượng"; color: colors.muted; font.pixelSize: 17
                            Layout.preferredWidth: 100 }
                    Button {
                        Layout.preferredWidth: root.tap; Layout.preferredHeight: root.tap
                        text: "−"; font.pixelSize: 28
                        onClicked: backend.setVolume(Math.max(0, (player.volume || 100) - 5))
                        background: Rectangle { radius: root.radius; color: parent.down ? colors.surface2 : colors.surface }
                        contentItem: Text { text: parent.text; font: parent.font
                            color: colors.text; horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter }
                    }
                    Slider {
                        id: volumeSlider
                        Layout.fillWidth: true
                        from: 0; to: 130; stepSize: 1
                        value: player.volume !== undefined ? player.volume : 100
                        onMoved: backend.setVolume(Math.round(value))
                        background: Rectangle {
                            x: volumeSlider.leftPadding; y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - 4
                            width: volumeSlider.availableWidth; height: 8; radius: 4
                            color: colors.surface2
                            Rectangle {
                                width: volumeSlider.visualPosition * parent.width
                                height: parent.height; radius: parent.radius
                                color: colors.accent
                            }
                        }
                        handle: Rectangle {
                            x: volumeSlider.leftPadding + volumeSlider.visualPosition * (volumeSlider.availableWidth - width)
                            y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - height / 2
                            width: 28; height: 28; radius: 14
                            color: colors.accent
                        }
                    }
                    Button {
                        Layout.preferredWidth: root.tap; Layout.preferredHeight: root.tap
                        text: "+"; font.pixelSize: 28
                        onClicked: backend.setVolume(Math.min(130, (player.volume || 100) + 5))
                        background: Rectangle { radius: root.radius; color: parent.down ? colors.surface2 : colors.surface }
                        contentItem: Text { text: parent.text; font: parent.font
                            color: colors.text; horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter }
                    }
                    Label {
                        text: player.volume !== undefined ? player.volume : 100
                        color: colors.accent; font.pixelSize: 20; font.bold: true
                        Layout.preferredWidth: 48
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                // --- Đổi tông ---
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    visible: player.capabilities ? player.capabilities.can_pitch : false
                    Label { text: "Tông"; color: colors.muted; font.pixelSize: 17
                            Layout.preferredWidth: 100 }
                    Button {
                        Layout.preferredWidth: root.tap; Layout.preferredHeight: root.tap
                        text: "−"; font.pixelSize: 28
                        onClicked: backend.setPitch((player.pitch || 0) - 1)
                        background: Rectangle { radius: root.radius; color: parent.down ? colors.surface2 : colors.surface }
                        contentItem: Text { text: parent.text; font: parent.font; color: colors.text
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: (player.pitch > 0 ? "+" : "") + (player.pitch || 0)
                        color: colors.accent; font.pixelSize: 22; font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Button {
                        Layout.preferredWidth: root.tap; Layout.preferredHeight: root.tap
                        text: "+"; font.pixelSize: 28
                        onClicked: backend.setPitch((player.pitch || 0) + 1)
                        background: Rectangle { radius: root.radius; color: parent.down ? colors.surface2 : colors.surface }
                        contentItem: Text { text: parent.text; font: parent.font; color: colors.text
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                    Label {
                        visible: player.capabilities && player.capabilities.pitch_quality === "dsp"
                        text: "Bài video: đổi tông nhiều sẽ hơi rè"
                        color: colors.muted; font.pixelSize: 13
                    }
                }

                // --- Hàng chờ thu gọn ---
                Label {
                    text: "Hàng chờ (" + (queue.items ? queue.items.length : 0) + ")"
                    color: colors.muted; font.pixelSize: 17
                }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; spacing: 10
                    model: queue.items || []
                    delegate: Rectangle {
                        width: ListView.view.width; height: 72
                        radius: root.radius; color: colors.surface
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 18
                            anchors.rightMargin: 12; spacing: 14
                            Label { text: index + 1; color: colors.muted
                                    font.pixelSize: 19; Layout.preferredWidth: 32 }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 2
                                Label { Layout.fillWidth: true; text: modelData.song.title
                                        color: colors.text; font.pixelSize: 18; elide: Text.ElideRight }
                                Label {
                                    text: (modelData.singer || modelData.song.channel || "")
                                          + (modelData.ready ? "" : "  ·  đang tải")
                                    color: colors.muted; font.pixelSize: 14
                                }
                            }
                            Button {
                                Layout.preferredWidth: 88; Layout.preferredHeight: root.tap - 8
                                text: "Xoá"
                                onClicked: backend.removeItem(modelData.id)
                                background: Rectangle { radius: 10
                                    color: parent.down ? "#3a1515" : colors.surface2 }
                                contentItem: Text { text: parent.text; color: colors.danger
                                    font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter }
                            }
                        }
                    }
                }
            }
        }

        // ====================================================== Tab 1: Tìm bài
        Item {
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 16

                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        placeholderText: "Tên bài hoặc ca sĩ…"
                        font.pixelSize: 20
                        color: colors.text
                        background: Rectangle { color: colors.surface
                            border.color: colors.surface2; radius: root.radius }
                        Keys.onReturnPressed: doSearch()
                        Keys.onEnterPressed: doSearch()
                    }
                    Button {
                        text: "Tìm"; font.pixelSize: 18; font.bold: true
                        Layout.preferredWidth: 100; Layout.preferredHeight: root.tap + 4
                        enabled: searchField.text.trim().length > 0
                        onClicked: doSearch()
                        background: Rectangle { radius: root.radius
                            color: parent.enabled ? (parent.down ? "#cc8c15" : colors.accent)
                                                  : colors.surface2 }
                        contentItem: Text { text: parent.text; font: parent.font
                            color: "#1a1206"; horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter }
                    }
                }

                Label {
                    id: searchStatus; text: ""; color: colors.muted; font.pixelSize: 15
                    visible: text !== ""
                }

                ListView {
                    id: searchList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; spacing: 10
                    model: searchResults

                    delegate: Rectangle {
                        width: ListView.view.width; height: 76
                        radius: root.radius; color: colors.surface
                        MouseArea {
                            anchors.fill: parent
                            onClicked: enqueueDialog.open(modelData)
                            onPressed: parent.color = colors.surface2
                            onReleased: parent.color = colors.surface
                            onCanceled: parent.color = colors.surface
                        }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 18
                            anchors.rightMargin: 16; spacing: 14
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 2
                                Label { Layout.fillWidth: true; text: modelData.title
                                        color: colors.text; font.pixelSize: 18; elide: Text.ElideRight }
                                Label {
                                    text: (modelData.channel || modelData.artist || "")
                                          + (modelData.duration
                                             ? "  ·  " + fmt(modelData.duration) : "")
                                          + (modelData.source === "local" ? "  · ✓ có sẵn" : "")
                                    color: colors.muted; font.pixelSize: 14
                                }
                            }
                            Label { text: "+"; color: colors.accent; font.pixelSize: 32; font.bold: true }
                        }
                    }
                    Label {
                        anchors.centerIn: parent
                        visible: searchList.count === 0 && searchStatus.text === ""
                        text: "Gõ tên bài và nhấn Tìm"
                        color: colors.muted; font.pixelSize: 18
                    }
                }
            }

            // Model tìm kiếm: backend gọi signal searchResults
            property var searchResults: []
            function doSearch() {
                if (!searchField.text.trim()) return
                searchStatus.text = "Đang tìm…"
                searchList.model = []
                backend.search(searchField.text.trim())
            }

            Connections {
                target: backend
                function onSearchResults(results, error) {
                    parent.searchResults = results
                    searchList.model = results
                    searchStatus.text = error || (results.length === 0 ? "Không tìm thấy bài nào." : "")
                }
            }
        }

        // ====================================================== Tab 2: Hàng chờ
        Item {
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 16

                Label {
                    text: "Hàng chờ  (" + (queue.items ? queue.items.length : 0) + " bài)"
                    color: colors.muted; font.pixelSize: 20; font.bold: true
                }

                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; spacing: 10
                    model: queue.items || []

                    header: queue.current ? queueCurrentDelegate : null
                    Component {
                        id: queueCurrentDelegate
                        Rectangle {
                            width: ListView.view ? ListView.view.width : 0; height: 88
                            radius: root.radius; color: "#221c0a"
                            border.color: "#3a2e17"
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 18
                                anchors.rightMargin: 18; spacing: 14
                                Label { text: "▶"; color: colors.accent; font.pixelSize: 22 }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 2
                                    Label { Layout.fillWidth: true
                                        text: queue.current ? queue.current.song.title : ""
                                        color: colors.text; font.pixelSize: 20; font.bold: true
                                        elide: Text.ElideRight }
                                    Label {
                                        text: (queue.current && queue.current.singer
                                               ? queue.current.singer + "  ·  " : "")
                                              + fmt(player.position) + " / " + fmt(player.duration)
                                        color: colors.muted; font.pixelSize: 15
                                    }
                                }
                            }
                        }
                    }

                    delegate: Rectangle {
                        width: ListView.view.width; height: 76
                        radius: root.radius; color: colors.surface
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 18
                            anchors.rightMargin: 12; spacing: 14
                            Label { text: index + 1; color: colors.muted
                                    font.pixelSize: 19; Layout.preferredWidth: 32 }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 2
                                Label { Layout.fillWidth: true; text: modelData.song.title
                                        color: colors.text; font.pixelSize: 18; elide: Text.ElideRight }
                                Label {
                                    text: (modelData.singer || modelData.song.channel || "")
                                          + (modelData.ready ? "" : "  ·  đang tải")
                                    color: colors.muted; font.pixelSize: 14
                                }
                            }
                            Button {
                                Layout.preferredWidth: 88; Layout.preferredHeight: root.tap - 8
                                text: "Xoá"
                                onClicked: backend.removeItem(modelData.id)
                                background: Rectangle { radius: 10
                                    color: parent.down ? "#3a1515" : colors.surface2 }
                                contentItem: Text { text: parent.text; color: colors.danger
                                    font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter }
                            }
                        }
                    }
                    Label {
                        anchors.centerIn: parent
                        visible: (queue.items ? queue.items.length : 0) === 0
                                 && !queue.current
                        text: "Hàng chờ trống"
                        color: colors.muted; font.pixelSize: 20
                    }
                }
            }
        }

        // ====================================================== Tab 3: Cài đặt
        Item {
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 24; spacing: 20

                Label { text: "Cài đặt"; color: colors.text; font.pixelSize: 26; font.bold: true }

                // --- Đổi vai trò màn hình ---
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        Label { text: "Đổi vai trò hai màn hình"; color: colors.text; font.pixelSize: 18 }
                        Label { text: "Hoán đổi màn cảm ứng và TV"; color: colors.muted; font.pixelSize: 14 }
                    }
                    Button {
                        text: "Đổi"; font.pixelSize: 17
                        Layout.preferredWidth: 100; Layout.preferredHeight: root.tap
                        onClicked: backend.swapDisplays()
                        background: Rectangle { radius: root.radius
                            color: parent.down ? colors.surface2 : colors.surface
                            border.color: colors.surface2 }
                        contentItem: Text { text: parent.text; font: parent.font; color: colors.text
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: colors.surface2 }

                // --- Cập nhật yt-dlp ---
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        Label { text: "Cập nhật yt-dlp"; color: colors.text; font.pixelSize: 18 }
                        Label { text: "Cần làm khi tìm YouTube không ra kết quả"
                                color: colors.muted; font.pixelSize: 14 }
                    }
                    Button {
                        id: ytdlpBtn; text: "Cập nhật"; font.pixelSize: 17
                        Layout.preferredWidth: 130; Layout.preferredHeight: root.tap
                        onClicked: {
                            ytdlpBtn.enabled = false
                            ytdlpStatus.text = "Đang cập nhật…"
                            backend.updateYtdlp()
                        }
                        background: Rectangle { radius: root.radius
                            color: parent.enabled
                                   ? (parent.down ? colors.surface2 : colors.surface)
                                   : "#1a1f2a"
                            border.color: colors.surface2 }
                        contentItem: Text { text: parent.text; font: parent.font
                            color: parent.enabled ? colors.text : colors.muted
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                }
                Label { id: ytdlpStatus; text: ""; color: colors.ok; font.pixelSize: 15; visible: text !== "" }

                Rectangle { Layout.fillWidth: true; height: 1; color: colors.surface2 }

                // --- Thông tin hệ thống ---
                Label {
                    text: "WiFi: " + (backend.connected ? "đang chạy" : "kiểm tra lại")
                          + "\nApp: http://192.168.50.1/"
                    color: colors.muted; font.pixelSize: 16; lineHeight: 1.5
                }

                Item { Layout.fillHeight: true }

                Connections {
                    target: backend
                    function onYtdlpUpdateDone(ok, detail) {
                        ytdlpBtn.enabled = true
                        ytdlpStatus.text = detail
                        ytdlpStatus.color = ok ? colors.ok : colors.danger
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- dialog đặt bài
    Popup {
        id: enqueueDialog
        property var song: null
        anchors.centerIn: parent
        width: 500; padding: 24
        modal: true

        background: Rectangle {
            color: colors.surface; radius: 18; border.color: colors.surface2
        }

        function open(s) { song = s; singerField.text = ""; visible = true; singerField.forceActiveFocus() }

        ColumnLayout {
            anchors.fill: parent; spacing: 16
            Label {
                Layout.fillWidth: true
                text: enqueueDialog.song ? enqueueDialog.song.title : ""
                color: colors.text; font.pixelSize: 20; font.bold: true; wrapMode: Text.WordWrap
            }
            Label { text: "Tên người hát (không bắt buộc)"
                    color: colors.muted; font.pixelSize: 15 }
            TextField {
                id: singerField; Layout.fillWidth: true
                font.pixelSize: 20; color: colors.text; maximumLength: 24
                background: Rectangle { color: colors.bg; radius: root.radius
                    border.color: colors.surface2 }
                Keys.onReturnPressed: confirmEnqueue()
                Keys.onEnterPressed:  confirmEnqueue()
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                Button {
                    Layout.fillWidth: true; Layout.preferredHeight: root.tap
                    text: "Huỷ"
                    onClicked: enqueueDialog.close()
                    background: Rectangle { radius: root.radius; color: parent.down ? colors.surface2 : colors.surface
                        border.color: colors.surface2 }
                    contentItem: Text { text: parent.text; color: colors.muted; font.pixelSize: 18
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
                Button {
                    Layout.fillWidth: true; Layout.preferredHeight: root.tap
                    text: "Đặt bài"; font.bold: true
                    onClicked: confirmEnqueue()
                    background: Rectangle { radius: root.radius; color: parent.down ? "#cc8c15" : colors.accent }
                    contentItem: Text { text: parent.text; font: parent.font; color: "#1a1206"
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
        }

        function confirmEnqueue() {
            if (!song) return
            backend.enqueue(song, singerField.text.trim())
            close()
            tabBar.currentIndex = 0   // quay về tab Đang phát
        }
    }
}
