import sys
import math
import xml.etree.ElementTree as ET
import re
from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage, QColor, QPalette, QFont, QPainter
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QCheckBox, QLabel, QLineEdit, QMessageBox
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_KEY_STATIC = '8888936f-e50b-4137-87db-6b521c398173'
API_KEY_GEOCODER = 'd504c2d0-69ab-4f12-a7e9-4158d5f66edc'


LIGHT_STYLE = """
QMainWindow { background-color: #f0f2f5; }
QPushButton { background-color: #4a90e2; color: white; border: none; border-radius: 5px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #357abd; }
QLineEdit { padding: 6px; border: 2px solid #bdc3c7; border-radius: 5px; font-size: 10pt; background-color: white; }
QLineEdit:focus { border-color: #4a90e2; }
QCheckBox { color: #2c3e50; font-weight: bold; font-size: 11pt; spacing: 5px; }
QLabel#g_map { border: 3px solid #bdc3c7; border-radius: 8px; background-color: #ecf0f1; }
QMenuBar { background-color: #ffffff; color: #2c3e50; }
QStatusBar { background-color: #ffffff; color: #7f8c8d; }
"""

DARK_STYLE = """
QMainWindow { background-color: #1a1a2e; }
QPushButton { background-color: #5d5fef; color: #ffffff; border: none; border-radius: 5px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #7273f2; }
QLineEdit { padding: 6px; border: 2px solid #4a4a6a; border-radius: 5px; font-size: 10pt; background-color: #252540; color: #e0e0ff; }
QLineEdit:focus { border-color: #5d5fef; }
QCheckBox { color: #e0e0ff; font-weight: bold; font-size: 11pt; spacing: 5px; }
QLabel#g_map { border: 3px solid #4a4a6a; border-radius: 8px; background-color: #252540; }
QMenuBar { background-color: #252540; color: #e0e0ff; }
QStatusBar { background-color: #252540; color: #a0a0c0; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('main_window.ui', self)

        self.map_zoom = 10
        self.map_ll = [37.617635, 55.755864]
        self.min_zoom, self.max_zoom = 1, 17
        self.min_lat, self.max_lat = -85.0, 85.0
        self.min_lon, self.max_lon = -180.0, 180.0
        self.map_width, self.map_height = 650, 450

        self.dark_theme = False
        self.theme_check = None
        self.search_point = None

        for name, method in [("PgUp", self.zoom_in), ("PgDown", self.zoom_out),
                             ("PgLeft", self.move_left), ("PgRight", self.move_right)]:
            btn = self.findChild(QPushButton, name)
            if btn: btn.clicked.connect(method)

        self.theme_check = self.findChild(QCheckBox, "themeToggle")
        if self.theme_check:
            self.theme_check.stateChanged.connect(self.toggle_theme)

        self.search_input = self.findChild(QLineEdit, "searchInput")
        self.search_btn = self.findChild(QPushButton, "searchBtn")

        if self.search_input:
            self.search_input.returnPressed.connect(self.search_object)
        if self.search_btn:
            self.search_btn.clicked.connect(self.search_object)

        self.apply_theme(False)
        self.refresh_map()

    def apply_theme(self, is_dark: bool):
        self.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)
        palette = QPalette()
        if is_dark:
            palette.setColor(QPalette.ColorRole.Window, QColor("#1a1a2e"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0ff"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#5d5fef"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#252540"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#e0e0ff"))
        else:
            palette.setColor(QPalette.ColorRole.Window, QColor("#f0f2f5"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#2c3e50"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#4a90e2"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#2c3e50"))
        self.setPalette(palette)

    def toggle_theme(self, state):
        self.dark_theme = (state == Qt.CheckState.Checked.value)
        self.apply_theme(self.dark_theme)
        self.refresh_map()

    def _set_map_position(self, lon, lat, zoom=15):
        self.search_point = [lon, lat]
        self.map_ll = [lon, lat]
        self.map_zoom = zoom
        self.refresh_map()

    def search_object(self):
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Поиск", "Введите запрос!")
            return

        geocoder_params = {
            "geocode": query,
            "apikey": API_KEY_GEOCODER,
            "format": "xml",
            "lang": "ru_RU",
            "results": 1
        }

        try:
            response = requests.get(
                "https://geocode-maps.yandex.ru/1.x/",
                params=geocoder_params,
                timeout=10
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

            xml_text = response.text
            xml_text = re.sub(r'\s+xmlns(:[^=]*)?="[^"]*"', '', xml_text)
            xml_text = re.sub(r'<(\w+):', r'<', xml_text)
            xml_text = re.sub(r'</(\w+):', r'</', xml_text)
            xml_text = re.sub(r'\s+\w+:[\w-]+="[^"]*"', '', xml_text)

            root = ET.fromstring(xml_text.encode('utf-8'))

            pos_elem = root.find(".//Point/pos")
            if pos_elem is None:
                pos_elem = root.find(".//pos")

            if pos_elem is None or not pos_elem.text or not pos_elem.text.strip():
                print("Не удалось найти координаты.")
                print(xml_text[:800])
                QMessageBox.warning(self, "Поиск", "Объект не найден. Попробуйте другой запрос.")
                return

            coords = pos_elem.text.strip().split()
            if len(coords) != 2:
                raise Exception(f"Неверный формат координат: '{pos_elem.text}'")

            lon, lat = map(float, coords)
            self._set_map_position(lon, lat)

        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "Ошибка сети", str(e))
        except ET.ParseError as e:
            print(f"Ошибка парсинга XML: {e}")
            QMessageBox.critical(self, "Ошибка", f"Неверный формат ответа")
        except Exception as e:
            QMessageBox.warning(self, "Поиск", f"{str(e)}")
            print(f"Ошибка поиска: {e}")

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
        new_lat = self.map_ll[1] + dlat
        if new_lat <= self.max_lat:
            self.map_ll[1] = new_lat
            self.search_point = None
            self.refresh_map()

    def move_down(self):
        _, dlat = self.calculate_offset()
        new_lat = self.map_ll[1] - dlat
        if new_lat >= self.min_lat:
            self.map_ll[1] = new_lat
            self.search_point = None
            self.refresh_map()

    def move_left(self):
        dlon, _ = self.calculate_offset()
        new_lon = self.map_ll[0] - dlon
        self.map_ll[0] = new_lon + 360.0 if new_lon < self.min_lon else new_lon
        self.search_point = None
        self.refresh_map()

    def move_right(self):
        dlon, _ = self.calculate_offset()
        new_lon = self.map_ll[0] + dlon
        self.map_ll[0] = new_lon - 360.0 if new_lon > self.max_lon else new_lon
        self.search_point = None
        self.refresh_map()

    def refresh_map(self):
        map_params = {
            "ll": f"{self.map_ll[0]:.6f},{self.map_ll[1]:.6f}",
            "z": self.map_zoom,
            "size": f"{self.map_width},{self.map_height}",
            "apikey": API_KEY_STATIC,
            "l": "map",
            "theme": "dark" if self.dark_theme else "light",
            "lang": "ru_RU",
        }

        if self.search_point:
            map_params["pt"] = f"{self.search_point[0]:.6f},{self.search_point[1]:.6f},pm2rdm"

        session = requests.Session()
        session.mount('https://', HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.5)))

        try:
            response = session.get('https://static-maps.yandex.ru/v1', params=map_params,
                                   headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if response.status_code != 200:
                self._show_placeholder(f"Ошибка карты {response.status_code}")
                return

            img = QImage.fromData(response.content)
            if img.isNull(): raise ValueError("Пустое изображение")

            self.g_map.setPixmap(QPixmap.fromImage(img))
            self.g_map.setScaledContents(True)

        except Exception as e:
            self._show_placeholder("Ошибка загрузки карты")

    def _show_placeholder(self, text: str):
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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
