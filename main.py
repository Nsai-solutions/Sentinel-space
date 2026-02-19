"""Orbital Propagator — Main Entry Point.

A real-time satellite orbit visualization tool using SGP4 propagation
with interactive 3D rendering via PyVista and PyQt6.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# MUST be set before any Qt/VTK imports
os.environ["QT_API"] = "pyqt6"

# Add project root to path for module imports
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging() -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quieter libraries
    logging.getLogger("pyvista").setLevel(logging.WARNING)
    logging.getLogger("vtk").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


def download_texture_background(data_dir: Path) -> None:
    """Download Earth texture in a background thread."""
    from PyQt6.QtCore import QThread

    class TextureDownloadThread(QThread):
        def __init__(self, data_dir: Path):
            super().__init__()
            self._data_dir = data_dir

        def run(self):
            try:
                from utils.downloader import Downloader

                downloader = Downloader(self._data_dir)
                result = downloader.download_earth_texture()
                if result.path:
                    logging.getLogger(__name__).info(
                        "Earth texture downloaded: %s", result.path
                    )
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to download Earth texture: %s", e
                )

    thread = TextureDownloadThread(data_dir)
    thread.start()
    return thread


def main() -> None:
    """Application entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Orbital Propagator")

    from PyQt6.QtWidgets import QApplication, QSplashScreen
    from PyQt6.QtGui import QPixmap, QFont, QColor, QPainter
    from PyQt6.QtCore import Qt, QTimer

    app = QApplication(sys.argv)
    app.setApplicationName("Orbital Propagator")
    app.setOrganizationName("OrbitalPropagator")

    # Load stylesheet
    style_path = PROJECT_ROOT / "assets" / "styles" / "theme.qss"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))
        logger.info("Loaded theme stylesheet")

    # Create splash screen
    splash_pixmap = QPixmap(450, 280)
    splash_pixmap.fill(QColor("#0A0A0F"))

    painter = QPainter(splash_pixmap)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 20, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(
        splash_pixmap.rect(),
        Qt.AlignmentFlag.AlignCenter,
        "Orbital Propagator",
    )
    font_small = QFont("Segoe UI", 11)
    painter.setFont(font_small)
    painter.setPen(QColor("#A3A3A3"))
    rect = splash_pixmap.rect()
    rect.moveTop(40)
    painter.drawText(
        rect,
        Qt.AlignmentFlag.AlignCenter,
        "Loading...",
    )
    painter.end()

    splash = QSplashScreen(splash_pixmap)
    splash.show()
    app.processEvents()

    # Data directory
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "tle_cache").mkdir(exist_ok=True)
    (data_dir / "textures").mkdir(exist_ok=True)

    # Start texture download in background
    texture_thread = download_texture_background(data_dir)

    # Create main window
    splash.showMessage(
        "Initializing 3D scene...",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#A3A3A3"),
    )
    app.processEvents()

    from ui.app import OrbitalPropagatorApp

    window = OrbitalPropagatorApp(data_dir)

    # Load default satellites
    splash.showMessage(
        "Loading satellites...",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#A3A3A3"),
    )
    app.processEvents()

    window.load_default_satellites()

    # Show main window
    splash.close()
    window.show()

    # Auto-start simulation
    window.sim_controller.play()
    window.sidebar.time_controls.set_playing(True)

    logger.info("Application ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
