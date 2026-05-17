import sys
import math
import xml.etree.ElementTree as ET
import re
from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage, QColor, QPalette, QFont, QPainter, QMouseEvent
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
QLabel#addressLabel { background-color: #ffffff; border: 2px solid #bdc3c7; border-radius: 5px; padding: 8px; color: #2c3e50; }
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
QLabel#addressLabel { background-color: #252540; border: 2px solid #4a4a6a; border-radius: 5px; padding: 8px; color: #e0e0ff; }
QMenuBar { background-color: #252540; color: #e0e0ff; }
QStatusBar { background-color: #252540; color: #a0a0c0; }
"""


class ClickableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setMouseTracking(True)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            click_x = event.pos().x()
            click_y = event.pos().y()

            lon, lat = self.pixel_to_coords(click_x, click_y)

            if self.parent_window:
                self.parent_window.search_by_click(lon, lat)

        super().mousePressEvent(event)

    def pixel_to_coords(self, px, py):
        if not self.parent_window:
            return 0, 0

        center_lon, center_lat = self.parent_window.map_ll
        zoom = self.parent_window.map_zoom
        width = self.parent_window.map_width
        height = self.parent_window.map_height

        scale_x = 360.0 / (256 * (2 ** zoom))
        scale_y = 180.0 / (256 * (2 ** zoom)) 
        dx = (px - width / 2) * scale_x
        dy = (height / 2 - py) * scale_y * math.cos(math.radians(center_lat))

        new_lon = center_lon + dx
        new_lat = center_lat + dy

        new_lat = max(-85.0, min(85.0, new_lat))

        while new_lon < -180.0:
            new_lon += 360.0
        while new_lon > 180.0:
            new_lon -= 360.0

        return new_lon, new_lat


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
        self.search_point = None

        self.found_address = ""
        self.found_postal_code = ""

        for name, method in [("PgUp", self.zoom_in), ("PgDown", self.zoom_out),
                             ("PgLeft", self.move_left), ("PgRight", self.move_right)]:
            btn = self.findChild(QPushButton, name)
            if btn: btn.clicked.connect(method)

        self.theme_check = self.findChild(QCheckBox, "themeToggle")
        if self.theme_check:
            self.theme_check.stateChanged.connect(self.toggle_theme)

        self.search_input = self.findChild(QLineEdit, "searchInput")
        self.search_btn = self.findChild(QPushButton, "searchBtn")
        if self.search_input: self.search_input.returnPressed.connect(self.search_object)
        if self.search_btn: self.search_btn.clicked.connect(self.search_object)

        old_map_label = self.findChild(QLabel, "g_map")
        if old_map_label:
            geometry = old_map_label.geometry()
            object_name = old_map_label.objectName()

            self.g_map = ClickableLabel(self)
            self.g_map.setGeometry(geometry)
            self.g_map.setObjectName(object_name)
            self.g_map.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.g_map.setWordWrap(True)

            old_map_label.deleteLater()
        else:
            self.g_map = ClickableLabel(self)

        self.address_label = self.findChild(QLabel, "addressLabel")
        if self.address_label:
            self.address_label.setText("Введите адрес для поиска или кликните на карту")
            self.address_label.setWordWrap(True)

        self.reset_btn = self.findChild(QPushButton, "resetSearchBtn")
        if self.reset_btn: self.reset_btn.clicked.connect(self.reset_search)

        self.apply_theme(False)
        self.statusBar().showMessage("Готово. Введите адрес для поиска или кликните на карту.")
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

    def _extract_address(self, root):
        try:
            formatted = root.find(".//Address/formatted")
            if formatted is not None and formatted.text:
                return formatted.text.strip()
            text_elem = root.find(".//GeocoderMetaData/text")
            if text_elem is not None and text_elem.text:
                return text_elem.text.strip()
            return "Адрес не определён"
        except Exception:
            return "Ошибка определения адреса"

    def _extract_postal_code(self, root):
        try:
            for path in [".//postal_code", ".//AddressComponent[kind='postal_code']/name"]:
                elem = root.find(path)
                if elem is not None and elem.text and elem.text.strip():
                    return elem.text.strip()
        except Exception:
            pass
        return ""

    def _set_map_position(self, lon, lat, zoom=15):
        self.search_point = [float(lon), float(lat)]
        self.map_ll = [float(lon), float(lat)]
        self.map_zoom = zoom
        self.refresh_map()

    def search_object(self):
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Поиск", "Введите запрос!")
            return

        geocoder_params = {
            "geocode": query, "apikey": API_KEY_GEOCODER,
            "format": "xml", "lang": "ru_RU", "results": 1
        }

        try:
            response = requests.get("https://geocode-maps.yandex.ru/1.x/", params=geocoder_params, timeout=10)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            xml_text = response.text
            xml_text = re.sub(r'\s+xmlns(:[^=]*)?="[^"]*"', '', xml_text)
            xml_text = re.sub(r'<(\w+):', r'<', xml_text)
            xml_text = re.sub(r'</(\w+):', r'</', xml_text)
            xml_text = re.sub(r'\s+\w+:[\w-]+="[^"]*"', '', xml_text)

            root = ET.fromstring(xml_text.encode('utf-8'))
            pos_elem = root.find(".//Point/pos")
            if pos_elem is None: pos_elem = root.find(".//pos")

            if pos_elem is None or not pos_elem.text or not pos_elem.text.strip():
                raise ValueError("Координаты не найдены")

            coords = pos_elem.text.strip().split()
            if len(coords) != 2: raise ValueError(f"Неверный формат: '{pos_elem.text}'")

            lon, lat = float(coords[0]), float(coords[1])

            self.found_address = self._extract_address(root)
            self.found_postal_code = self._extract_postal_code(root)

            if self.found_postal_code:
                display_text = f"{self.found_address}, индекс: {self.found_postal_code}"
            else:
                display_text = f"{self.found_address}"

            if self.address_label:
                self.address_label.setText(display_text)

            self._set_map_position(lon, lat)
            self.statusBar().showMessage(f"Найдено: {self.found_address[:40]}...")

        except Exception as e:
            QMessageBox.warning(self, "Поиск", f"Ошибка: {str(e)}")
            print(f"Ошибка поиска: {e}")

    def search_by_click(self, lon, lat):
        self.statusBar().showMessage(f"Поиск адреса по координатам: {lon:.6f}, {lat:.6f}...")

        self.search_point = None
        self.found_address = ""
        self.found_postal_code = ""

        geocoder_params = {
            "geocode": f"{lon},{lat}",
            "apikey": API_KEY_GEOCODER,
            "format": "xml",
            "lang": "ru_RU",
            "results": 1,
            "kind": "house" 
        }

        try:
            response = requests.get("https://geocode-maps.yandex.ru/1.x/", params=geocoder_params, timeout=10)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            xml_text = response.text
            xml_text = re.sub(r'\s+xmlns(:[^=]*)?="[^"]*"', '', xml_text)
            xml_text = re.sub(r'<(\w+):', r'<', xml_text)
            xml_text = re.sub(r'</(\w+):', r'</', xml_text)
            xml_text = re.sub(r'\s+\w+:[\w-]+="[^"]*"', '', xml_text)

            root = ET.fromstring(xml_text.encode('utf-8'))
            pos_elem = root.find(".//Point/pos")
            if pos_elem is None: pos_elem = root.find(".//pos")

            if pos_elem is None or not pos_elem.text or not pos_elem.text.strip():
                self.found_address = f"Координаты: {lat:.6f}, {lon:.6f}"
                self.found_postal_code = ""
                display_text = f"{self.found_address}"
                if self.address_label:
                    self.address_label.setText(display_text)

                self.search_point = [lon, lat]
                self.refresh_map()
                self.statusBar().showMessage("Точный адрес не найден, показаны координаты")
                return

            coords = pos_elem.text.strip().split()
            if len(coords) != 2: raise ValueError(f"Неверный формат: '{pos_elem.text}'")

            found_lon, found_lat = float(coords[0]), float(coords[1])

            self.found_address = self._extract_address(root)
            self.found_postal_code = self._extract_postal_code(root)

            if self.found_postal_code:
                display_text = f"{self.found_address}, индекс: {self.found_postal_code}"
            else:
                display_text = f"{self.found_address}"

            if self.address_label:
                self.address_label.setText(display_text)

            self.search_point = [found_lon, found_lat]
            self.refresh_map()

            self.statusBar().showMessage(f"Клик: {self.found_address[:40]}...")

        except Exception as e:
            QMessageBox.warning(self, "Поиск по клику", f"Ошибка: {str(e)}")
            print(f"Ошибка поиска по клику: {e}")

    def reset_search(self):
        self.search_point = None
        self.found_address = ""
        self.found_postal_code = ""
        if self.address_label:
            self.address_label.setText("Введите адрес для поиска или кликните на карту")
        self.refresh_map()
        self.statusBar().showMessage("Результат поиска сброшен")

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
            self.refresh_map()

    def move_down(self):
        _, dlat = self.calculate_offset()
        new_lat = self.map_ll[1] - dlat
        if new_lat >= self.min_lat:
            self.map_ll[1] = new_lat
            self.refresh_map()

    def move_left(self):
        dlon, _ = self.calculate_offset()
        new_lon = self.map_ll[0] - dlon
        self.map_ll[0] = new_lon + 360.0 if new_lon < self.min_lon else new_lon
        self.refresh_map()

    def move_right(self):
        dlon, _ = self.calculate_offset()
        new_lon = self.map_ll[0] + dlon
        self.map_ll[0] = new_lon - 360.0 if new_lon > self.max_lon else new_lon
        self.refresh_map()

    def refresh_map(self):
        from urllib.parse import urlencode
        map_params = {
            "ll": f"{self.map_ll[0]:.6f},{self.map_ll[1]:.6f}",
            "z": self.map_zoom,
            "size": f"{self.map_width},{self.map_height}",
            "apikey": API_KEY_STATIC,
            "l": "map",
            "theme": "dark" if self.dark_theme else "light",
            "lang": "ru_RU"
        }

        if self.search_point is not None:
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
            self.g_map.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.g_map.setScaledContents(False)

        except Exception as e:
            print(f"Ошибка: {e}")
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
        self.g_map.setAlignment(Qt.AlignmentFlag.AlignCenter)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
