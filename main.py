import sys
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

        # Параметры карты
        self.map_zoom = 10
        self.map_ll = [37.77751, 54.757718]
        self.min_zoom = 1
        self.max_zoom = 17

        # Подключение кнопок из интерфейса
        self.PgUp_btn = self.findChild(QPushButton, "PgUp")
        if self.PgUp_btn:
            self.PgUp_btn.clicked.connect(self.zoom_in)

        self.PgDown_btn = self.findChild(QPushButton, "PgDown")
        if self.PgDown_btn:
            self.PgDown_btn.clicked.connect(self.zoom_out)

        self.refresh_map()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_PageUp:
            self.zoom_in()
        elif event.key() == Qt.Key.Key_PageDown:
            self.zoom_out()
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

    def refresh_map(self):
        map_params = {
            "ll": f"{self.map_ll[0]},{self.map_ll[1]}",
            "z": self.map_zoom,
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

        except requests.RequestException as e:
            print(f"Ошибка загрузки карты: {e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())