import sys
import math
from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_KEY_STATIC = '8888936f-e50b-4137-87db-6b521c398173'


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('main_window.ui', self)

        self.map_zoom = 10
        self.map_ll = [37.77751, 54.757718]
        self.min_zoom = 1
        self.max_zoom = 17

        self.min_lat = -85.0
        self.max_lat = 85.0
        self.min_lon = -180.0
        self.max_lon = 180.0

        self.map_width = 650  
        self.map_height = 450  

        self.PgUp_btn = self.findChild(QPushButton, "PgUp")
        if self.PgUp_btn:
            self.PgUp_btn.clicked.connect(self.zoom_in)

        self.PgDown_btn = self.findChild(QPushButton, "PgDown")
        if self.PgDown_btn:
            self.PgDown_btn.clicked.connect(self.zoom_out)

        self.PgLeft_btn = self.findChild(QPushButton, "PgLeft")
        if self.PgLeft_btn:
            self.PgLeft_btn.clicked.connect(self.move_left)

        self.PgRight_btn = self.findChild(QPushButton, "PgRight")
        if self.PgRight_btn:
            self.PgRight_btn.clicked.connect(self.move_right)

        self.refresh_map()

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

        delta_lon = 360.0 / (2 ** self.map_zoom) * (self.map_width / 256) * 0.7

        lat_rad = math.radians(self.map_ll[1])
        delta_lat = delta_lon * math.cos(lat_rad)

        return delta_lon, delta_lat

    def move_up(self):
        _, delta_lat = self.calculate_offset()
        new_lat = self.map_ll[1] + delta_lat

        if new_lat <= self.max_lat:
            self.map_ll[1] = new_lat
            self.refresh_map()

    def move_down(self):
        _, delta_lat = self.calculate_offset()
        new_lat = self.map_ll[1] - delta_lat

        if new_lat >= self.min_lat:
            self.map_ll[1] = new_lat
            self.refresh_map()

    def move_left(self):
        delta_lon, _ = self.calculate_offset()
        new_lon = self.map_ll[0] - delta_lon

        if new_lon < self.min_lon:
            new_lon += 360.0

        self.map_ll[0] = new_lon
        self.refresh_map()

    def move_right(self):
        delta_lon, _ = self.calculate_offset()
        new_lon = self.map_ll[0] + delta_lon

        if new_lon > self.max_lon:
            new_lon -= 360.0

        self.map_ll[0] = new_lon
        self.refresh_map()

    def refresh_map(self):
        map_params = {
            "ll": f"{self.map_ll[0]:.6f},{self.map_ll[1]:.6f}", 
            "z": self.map_zoom,
            "size": f"{self.map_width},{self.map_height}",
            "apikey": API_KEY_STATIC,
        }

        session = requests.Session()
        retry = Retry(total=10, connect=5, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        try:
            response = session.get(
                'https://static-maps.yandex.ru/v1',
                params=map_params,
                timeout=10
            )
            response.raise_for_status()

            img = QImage.fromData(response.content)
            pixmap = QPixmap.fromImage(img)
            self.g_map.setPixmap(pixmap)
            self.g_map.setScaledContents(True)  
        except requests.RequestException as e:
            print(f"Ошибка загрузки карты: {e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
