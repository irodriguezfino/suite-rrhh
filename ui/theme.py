"""Tema visual centralizado de la aplicacion."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette

APP_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = APP_DIR / "assets"
APP_ICON = ASSETS_DIR / "ICONO_SUITE_RRHH.ico"
RODRIGUEZ_LOGO = ASSETS_DIR / "RODRIGUEZ.png"
FINURA_LOGO = ASSETS_DIR / "FINURA.png"

COLORS = {
    "primary": "#123283",
    "primary_hover": "#1B3891",
    "primary_pressed": "#0B235F",
    "background": "#F5F7FB",
    "surface": "#FFFFFF",
    "text": "#172033",
    "muted": "#52627A",
    "border": "#D7DFEF",
    "focus": "#2F6FED",
    "success": "#087A4A",
    "warning": "#A85A00",
    "danger": "#C32421",
    "danger_hover": "#9F1A1A",
    "info_surface": "#EEF3FD",
}


def apply_application_style(app) -> None:
    """Aplica una apariencia consistente, con foco y contraste visibles."""
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["background"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor("#F3F6FA"))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["primary"]))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        * {{ font-family: 'Segoe UI'; font-size: 11pt; color: {COLORS['text']}; }}
        QMainWindow, QDialog {{ background: {COLORS['background']}; }}
        QWidget#pageSurface, QFrame#card, QGroupBox {{ background: {COLORS['surface']}; }}
        QFrame#card {{ border: 1px solid {COLORS['border']}; border-radius: 12px; }}
        QFrame#compactPanel {{ background: #F8FAFE; border: 1px solid {COLORS['border']}; border-radius: 9px; }}
        QFrame#actionCard {{ background: #EEF3FD; border: 1px solid #C8D7F3; border-radius: 10px; }}
        QFrame#activityCard {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 10px; }}
        QGroupBox {{ border: 1px solid {COLORS['border']}; border-radius: 10px; margin-top: 12px; padding: 14px; font-weight: 600; color: {COLORS['primary']}; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
        QLineEdit, QDateEdit, QPlainTextEdit, QTableWidget {{ background: #FFFFFF; border: 1px solid {COLORS['border']}; border-radius: 7px; padding: 7px; selection-background-color: {COLORS['primary']}; }}
        QLineEdit:focus, QDateEdit:focus, QPlainTextEdit:focus, QTableWidget:focus, QPushButton:focus, QToolButton:focus {{ border: 2px solid {COLORS['focus']}; }}
        QPushButton {{ background: #FFFFFF; border: 1px solid {COLORS['border']}; border-radius: 7px; padding: 8px 14px; min-height: 22px; }}
        QPushButton:hover {{ background: #F0F4FB; border-color: #A9BBDD; }}
        QPushButton:pressed {{ background: #E5ECF8; }}
        QPushButton:disabled {{ color: #7A8495; background: #EEF1F5; border-color: #E2E6EC; }}
        QPushButton#primaryButton {{ background: {COLORS['primary']}; border-color: {COLORS['primary']}; color: #FFFFFF; font-weight: 700; }}
        QPushButton#primaryButton:hover {{ background: {COLORS['primary_hover']}; }}
        QPushButton#primaryButton:pressed {{ background: {COLORS['primary_pressed']}; }}
        QPushButton#dangerButton {{ background: {COLORS['danger']}; border-color: {COLORS['danger']}; color: #FFFFFF; }}
        QPushButton#dangerButton:hover {{ background: {COLORS['danger_hover']}; }}
        QToolBar {{ background: #FFFFFF; border: 0; border-bottom: 1px solid {COLORS['border']}; spacing: 6px; padding: 7px; }}
        QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 7px 10px; }}
        QToolButton:hover {{ background: #EEF3FD; }}
        QLabel#toolbarTitle {{ font-size: 13pt; font-weight: 700; color: {COLORS['primary']}; }}
        QLabel#homeTitle {{ font-size: 25pt; font-weight: 700; color: {COLORS['primary']}; }}
        QLabel#homeHeading {{ font-size: 15pt; font-weight: 700; }}
        QHeaderView::section {{ background: #EEF3FD; color: {COLORS['primary']}; border: 0; border-bottom: 1px solid {COLORS['border']}; padding: 8px; font-weight: 700; }}
        QProgressBar {{ border: 1px solid {COLORS['border']}; border-radius: 7px; text-align: center; background: #E7EDF8; min-height: 19px; font-weight: 600; }}
        QProgressBar::chunk {{ background: {COLORS['primary']}; border-radius: 5px; }}
        QLabel#mutedLabel {{ color: {COLORS['muted']}; }}
        QLabel#pageTitle {{ font-size: 21pt; font-weight: 700; color: {COLORS['text']}; }}
        QLabel#sectionLabel {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#modeBadge {{ color: {COLORS['primary']}; background: #E6EEFF; border-radius: 9px; padding: 5px 9px; font-size: 9pt; font-weight: 700; }}
        QLabel#summaryLabel {{ color: {COLORS['text']}; padding: 4px 2px; }}
        QLabel#activityPending, QLabel#activityReady, QLabel#activityRunning, QLabel#activitySuccess, QLabel#activityWarning {{ border-radius: 9px; padding: 5px 9px; font-size: 9pt; font-weight: 700; }}
        QLabel#activityPending {{ color: {COLORS['muted']}; background: #EFF2F7; }}
        QLabel#activityReady, QLabel#activityRunning {{ color: {COLORS['primary']}; background: #E6EEFF; }}
        QLabel#activitySuccess {{ color: {COLORS['success']}; background: #EAF8F0; }}
        QLabel#activityWarning {{ color: {COLORS['warning']}; background: #FFF4E5; }}
        QLabel#statusInfo {{ color: {COLORS['primary']}; background: {COLORS['info_surface']}; border-radius: 6px; padding: 9px; }}
        QLabel#statusSuccess {{ color: {COLORS['success']}; background: #ECFDF3; border-radius: 6px; padding: 9px; }}
        QLabel#statusWarning {{ color: {COLORS['warning']}; background: #FFF7ED; border-radius: 6px; padding: 9px; }}
    """)
