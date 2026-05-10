import sys
import math
from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage, QColor, QPalette, QFont, QPainter
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QCheckBox, QLabel
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_KEY_STATIC = '8888936f-e50b-4137-87db-6b521c398173'

LIGHT_STYLE = """
QMainWindow { background-color: #f0f2f5; }
QPushButton { background-color: #4a90e2; color: white; border: none; border-radius: 5px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #357abd; }
QCheckBox { color: #2c3e50; font-weight: bold; font-size: 11pt; }
QLabel#g_map { border: 3px solid #bdc3c7; border-radius: 8px; background-color: #ecf0f1; }
QMenuBar { background-color: #ffffff; color: #2c3e50; }
QStatusBar { background-color: #ffffff; color: #7f8c8d; }
"""

DARK_STYLE = """
QMainWindow { background-color: #1a1a2e; }
QPushButton { background-color: #5d5fef; color: #ffffff; border: none; border-radius: 5px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #7273f2; }
QCheckBox { color: #e0e0ff; font-weight: bold; font-size: 11pt; }
QLabel#g_map { border: 3px solid #4a4a6a; border-radius: 8px; background-color: #252540; }
QMenuBar { background-color: #252540; color: #e0e0ff; }
QStatusBar { background-color: #252540; color: #a0a0c0; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('main_window.ui', self)

        self.map_zoom = 10
        self.map_ll = [37.77751, 54.757718]
        self.min_zoom, self.max_zoom = 1, 17
        self.min_lat, self.max_lat = -85.0, 85.0
        self.min_lon, self.max_lon = -180.0, 180.0
        self.map_width, self.map_height = 650, 450
        self.dark_theme = False
        self.theme_check = None

        for name, method in [("PgUp", self.zoom_in), ("PgDown", self.zoom_out),
                             ("PgLeft", self.move_left), ("PgRight", self.move_right)]:
            btn = self.findChild(QPushButton, name)
            if btn: btn.clicked.connect(method)

        self.theme_check = self.findChild(QCheckBox, "themeToggle")
        if self.theme_check:
            self.theme_check.stateChanged.connect(self.toggle_theme)

        self.overlay = QLabel(self.centralwidget)
        self.overlay.setGeometry(10, 90, self.map_width, self.map_height)
        self.overlay.setStyleSheet("background-color: rgba(30, 30, 50, 100);")
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay.hide()
        self.overlay.raise_()

        self.apply_theme(False)
        if API_KEY_STATIC.strip():
            self.refresh_map()

    def apply_theme(self, is_dark: bool):
        self.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)
        p = QPalette()
        if is_dark:
            p.setColor(QPalette.ColorRole.Window, QColor("#1a1a2e"))
            p.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0ff"))
            p.setColor(QPalette.ColorRole.Button, QColor("#5d5fef"))
            p.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        else:
            p.setColor(QPalette.ColorRole.Window, QColor("#f0f2f5"))
            p.setColor(QPalette.ColorRole.WindowText, QColor("#2c3e50"))
            p.setColor(QPalette.ColorRole.Button, QColor("#4a90e2"))
            p.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        self.setPalette(p)

    def show_placeholder(self, text: str):
        pm = QPixmap(self.map_width, self.map_height)
        bg = QColor("#2d2d44" if self.dark_theme else "#e8e8e8")
        fg = QColor("#a0a0ff" if self.dark_theme else "#2c3e50")
        pm.fill(bg)
        painter = QPainter(pm)
        painter.setPen(fg)
        painter.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        self.g_map.setPixmap(pm)
        self.g_map.setScaledContents(True)
        self.overlay.setGeometry(self.g_map.geometry())

    def toggle_theme(self, state):
        self.dark_theme = (state == Qt.CheckState.Checked.value)
        self.apply_theme(self.dark_theme)
        self.overlay.setVisible(self.dark_theme)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_PageUp:
            self.zoom_in()
        elif key == Qt.Key.Key_PageDown:
            self.zoom_out()
        elif key == Qt.Key.Key_Up:
            self.move_up()
        elif key == Qt.Key.Key_Down:
            self.move_down()
        elif key == Qt.Key.Key_Left:
            self.move_left()
        elif key == Qt.Key.Key_Right:
            self.move_right()
        else:
            super().keyPressEvent(event)

    def zoom_in(self):
        if self.map_zoom < self.max_zoom:
            self.map_zoom += 1
            self.refresh_map()

    def zoom_out(self):
        if self.map_zoom > self.min_zoom:
            self.map_zoom -= 1
            self.refresh_map()

    def calculate_offset(self):
        dlon = 360.0 / (2 ** self.map_zoom) * (self.map_width / 256) * 0.7
        dlat = dlon * math.cos(math.radians(self.map_ll[1]))
        return dlon, dlat

    def move_up(self):
        _, dlat = self.calculate_offset()
        new = self.map_ll[1] + dlat
        if new <= self.max_lat:
            self.map_ll[1] = new
            self.refresh_map()

    def move_down(self):
        _, dlat = self.calculate_offset()
        new = self.map_ll[1] - dlat
        if new >= self.min_lat:
            self.map_ll[1] = new
            self.refresh_map()

    def move_left(self):
        dlon, _ = self.calculate_offset()
        new = self.map_ll[0] - dlon
        self.map_ll[0] = new + 360.0 if new < self.min_lon else new
        self.refresh_map()

    def move_right(self):
        dlon, _ = self.calculate_offset()
        new = self.map_ll[0] + dlon
        self.map_ll[0] = new - 360.0 if new > self.max_lon else new
        self.refresh_map()

    def refresh_map(self):
        if not API_KEY_STATIC.strip():
            return

        layer = "sat" if self.dark_theme else "map"
        params = {
            "ll": f"{self.map_ll[0]:.6f},{self.map_ll[1]:.6f}",
            "z": self.map_zoom, "size": f"{self.map_width},{self.map_height}",
            "apikey": API_KEY_STATIC, "l": layer, "lang": "ru_RU"
        }
        try:
            s = requests.Session()
            s.mount('https://', HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.5)))
            r = s.get('https://static-maps.yandex.ru/v1', params=params, timeout=10,
                      headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code != 200:
                print(f"Ошибка {r.status_code}: {r.text[:200]}")
                self.show_placeholder(f"Ошибка {r.status_code}\nПроверьте API-ключ")
                return
            img = QImage.fromData(r.content)
            if not img.isNull():
                self.g_map.setPixmap(QPixmap.fromImage(img))
                self.g_map.setScaledContents(True)
                self.overlay.setGeometry(self.g_map.geometry())
        except Exception as e:
            print(f"Ошибка: {e}")
            self.show_placeholder("Не удалось загрузить карту")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
