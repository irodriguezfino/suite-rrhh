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
    calendar_chevron = (ASSETS_DIR / "calendar_chevron.svg").as_posix()
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
        QFrame#comparisonSetupCard, QFrame#comparisonProgressCard, QFrame#resultPreviewCard {{ background: #FFFFFF; border: 1px solid {COLORS['border']}; border-radius: 14px; }}
        QFrame#helpHero {{ background: #EAF0FC; border: 1px solid #C9D8F4; border-radius: 12px; }}
        QFrame#helpStepCard {{ background: #FFFFFF; border: 1px solid #D7E0F0; border-radius: 10px; }}
        QFrame#helpFormulaCard {{ background: #F7F9FD; border: 1px solid #D7E0F0; border-radius: 10px; }}
        QFrame#helpChecklistCard {{ background: #F7F9FD; border: 1px solid #D7E0F0; border-radius: 10px; }}
        QFrame#helpStateCard {{ background: #FFFFFF; border: 1px solid #D7E0F0; border-radius: 10px; }}
        QFrame#helpCalloutInfo {{ background: #EEF3FD; border: 1px solid #C9D8F4; border-radius: 9px; }}
        QFrame#helpCalloutSuccess {{ background: #ECFDF3; border: 1px solid #B9E8CE; border-radius: 9px; }}
        QFrame#helpCalloutWarning {{ background: #FFF7E9; border: 1px solid #F0D49C; border-radius: 9px; }}
        QFrame#helpCalloutDanger {{ background: #FFF0F0; border: 1px solid #F0C4C4; border-radius: 9px; }}
        QFrame#comparisonSetupCard {{ min-width: 680px; }}
        QFrame#preparationIntroPanel {{ background: #F4F7FD; border: 1px solid #DCE5F4; border-radius: 11px; }}
        QFrame#sourceSelectionPanel {{ background: #FFFFFF; border: 1px solid #D6E0F2; border-radius: 11px; }}
        QFrame#comparisonSummaryCard {{ background: #FFFFFF; border: 1px solid #D2DDF0; border-radius: 9px; }}
        QFrame#sourceSelectorCard {{ background: #F8FAFE; border: 1px solid #D6E0F2; border-radius: 11px; }}
        QFrame#sourceSelectorCard:hover {{ background: #F2F6FE; border-color: #A9BBDD; }}
        QFrame#sourceContextBar {{ background: #F8FAFE; border: 1px solid {COLORS['border']}; border-radius: 10px; }}
        QFrame#processingStepsPanel {{ background: #F8FAFE; border: 1px solid #DCE5F4; border-radius: 10px; }}
        QLineEdit, QDateEdit, QPlainTextEdit, QTableWidget {{ background: #FFFFFF; border: 1px solid {COLORS['border']}; border-radius: 7px; padding: 7px; selection-background-color: {COLORS['primary']}; }}
        QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 34px; background: #E6EEFF; border-left: 1px solid #C8D7F3; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
        QDateEdit::drop-down:hover {{ background: #DCE8FF; }}
        QDateEdit::down-arrow {{ image: url(\"{calendar_chevron}\"); width: 16px; height: 10px; }}
        QCalendarWidget#dateCalendar {{ background: #FFFFFF; border: 1px solid #C8D7F3; border-radius: 12px; padding: 6px; }}
        QCalendarWidget#dateCalendar QWidget {{ background: #FFFFFF; color: {COLORS['text']}; }}
        QCalendarWidget#dateCalendar QWidget#qt_calendar_navigationbar {{ background: #EEF3FD; border: 0; border-bottom: 1px solid #D5E1F7; border-top-left-radius: 8px; border-top-right-radius: 8px; min-height: 38px; }}
        QCalendarWidget#dateCalendar QToolButton {{ color: {COLORS['primary']}; background: transparent; border: 0; border-radius: 6px; padding: 6px 8px; font-weight: 700; }}
        QCalendarWidget#dateCalendar QToolButton:hover {{ background: #DCE8FF; }}
        QCalendarWidget#dateCalendar QToolButton#qt_calendar_prevmonth, QCalendarWidget#dateCalendar QToolButton#qt_calendar_nextmonth {{ background: #FFFFFF; border: 1px solid #C8D7F3; border-radius: 14px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0; }}
        QCalendarWidget#dateCalendar QToolButton#qt_calendar_prevmonth:hover, QCalendarWidget#dateCalendar QToolButton#qt_calendar_nextmonth:hover {{ background: #DCE8FF; border-color: #8FABE0; }}
        QCalendarWidget#dateCalendar QToolButton#qt_calendar_monthbutton, QCalendarWidget#dateCalendar QToolButton#qt_calendar_yearbutton {{ font-size: 11pt; color: {COLORS['primary']}; padding: 6px 5px; }}
        QCalendarWidget#dateCalendar QAbstractItemView {{ background: #FFFFFF; color: {COLORS['text']}; selection-background-color: #2F6FED; selection-color: #FFFFFF; outline: 0; font-size: 10pt; alternate-background-color: #F7F9FD; }}
        QCalendarWidget#dateCalendar QAbstractItemView::item {{ border-radius: 6px; margin: 2px; padding: 4px; }}
        QCalendarWidget#dateCalendar QAbstractItemView::item:selected {{ background: #2F6FED; color: #FFFFFF; font-weight: 700; }}
        QCalendarWidget#dateCalendar QAbstractItemView::item:hover {{ background: #DCE8FF; color: #172033; }}
        QCalendarWidget#dateCalendar QHeaderView::section {{ background: #FFFFFF; color: #52627A; border: 0; padding: 7px 3px 4px; font-size: 9pt; font-weight: 700; }}
        QCalendarWidget#dateCalendar QMenu {{ background: #FFFFFF; color: {COLORS['text']}; border: 1px solid {COLORS['border']}; border-radius: 7px; padding: 4px; }}
        QCalendarWidget#dateCalendar QMenu::item:selected {{ background: #DCE8FF; color: {COLORS['primary']}; border-radius: 4px; }}
        QCalendarWidget#dateCalendar QSpinBox {{ background: #FFFFFF; color: {COLORS['text']}; border: 1px solid #C8D7F3; border-radius: 6px; padding: 4px 6px; min-width: 74px; }}
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
        QToolButton#rowRemoveButton {{ color: {COLORS['danger']}; background: #FFF1F1; border: 1px solid #F3C7C7; border-radius: 14px; padding: 0; font-size: 16pt; font-weight: 500; }}
        QToolButton#rowRemoveButton:hover {{ color: #FFFFFF; background: {COLORS['danger']}; border-color: {COLORS['danger']}; }}
        QToolButton#rowRemoveButton:pressed {{ background: {COLORS['danger_hover']}; }}
        QLabel#toolbarTitle {{ font-size: 13pt; font-weight: 700; color: {COLORS['primary']}; }}
        QLabel#homeTitle {{ font-size: 25pt; font-weight: 700; color: {COLORS['primary']}; }}
        QLabel#homeHeading {{ font-size: 15pt; font-weight: 700; }}
        QHeaderView::section {{ background: #EEF3FD; color: {COLORS['primary']}; border: 0; border-bottom: 1px solid {COLORS['border']}; padding: 8px; font-weight: 700; }}
        QProgressBar {{ border: 1px solid {COLORS['border']}; border-radius: 7px; text-align: center; background: #E7EDF8; min-height: 19px; font-weight: 600; }}
        QProgressBar::chunk {{ background: {COLORS['primary']}; border-radius: 5px; }}
        QTabWidget#comparadorHelpTabs::pane {{ background: #FFFFFF; border: 1px solid {COLORS['border']}; border-radius: 10px; top: -1px; }}
        QTabWidget#comparadorHelpTabs QTabBar::tab {{ background: #EDF2FA; color: {COLORS['muted']}; border: 1px solid #D7E0F0; border-bottom: 0; border-top-left-radius: 8px; border-top-right-radius: 8px; padding: 9px 14px; margin-right: 3px; font-weight: 600; }}
        QTabWidget#comparadorHelpTabs QTabBar::tab:selected {{ background: #FFFFFF; color: {COLORS['primary']}; font-weight: 700; }}
        QTabWidget#comparadorHelpTabs QTabBar::tab:hover {{ background: #E4ECFA; color: {COLORS['primary']}; }}
        QLabel#mutedLabel {{ color: {COLORS['muted']}; }}
        QLabel#pageTitle {{ font-size: 21pt; font-weight: 700; color: {COLORS['text']}; }}
        QLabel#helpHeroTitle {{ color: {COLORS['primary']}; font-size: 18pt; font-weight: 700; }}
        QLabel#helpHeroSubtitle {{ color: {COLORS['muted']}; font-size: 11pt; }}
        QLabel#helpSectionTitle {{ color: {COLORS['primary']}; font-size: 14pt; font-weight: 700; }}
        QLabel#helpBody {{ color: {COLORS['text']}; }}
        QLabel#helpStepNumber {{ color: #FFFFFF; background: {COLORS['primary']}; border-radius: 13px; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; font-size: 10pt; font-weight: 800; qproperty-alignment: AlignCenter; }}
        QLabel#helpCardTitle {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#helpCardText {{ color: {COLORS['muted']}; font-size: 10pt; }}
        QLabel#helpCalloutTitle {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#helpCalloutText {{ color: {COLORS['text']}; font-size: 10pt; }}
        QLabel#helpFormulaSource {{ color: {COLORS['text']}; background: #FFFFFF; border: 1px solid #D7E0F0; border-radius: 7px; padding: 9px 12px; font-weight: 700; }}
        QLabel#helpFormulaOperator {{ color: {COLORS['primary']}; font-size: 18pt; font-weight: 700; }}
        QLabel#helpFormulaResult {{ color: #FFFFFF; background: {COLORS['primary']}; border-radius: 7px; padding: 9px 12px; font-weight: 700; }}
        QLabel#helpGridHeader {{ color: {COLORS['primary']}; background: #EAF0FC; border-radius: 5px; padding: 7px 8px; font-size: 10pt; font-weight: 700; }}
        QLabel#helpGridCell {{ color: {COLORS['text']}; border-bottom: 1px solid #E5EAF3; padding: 7px 8px; font-size: 10pt; }}
        QLabel#helpChecklistItem {{ color: {COLORS['text']}; padding: 3px 0; }}
        QLabel#helpStateKey {{ color: {COLORS['muted']}; font-size: 10pt; }}
        QLabel#helpStateValue {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#sectionLabel {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#modeBadge {{ color: {COLORS['primary']}; background: #E6EEFF; border-radius: 9px; padding: 5px 9px; font-size: 9pt; font-weight: 700; }}
        QLabel#stateTitle {{ font-size: 20pt; font-weight: 700; color: {COLORS['text']}; }}
        QLabel#stateSubtitle {{ color: {COLORS['muted']}; font-size: 11pt; }}
        QLabel#preparationOutcome {{ color: {COLORS['primary']}; background: #E6EEFF; border-radius: 8px; padding: 10px 12px; }}
        QLabel#summaryCardTitle {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#summaryCardText {{ color: {COLORS['text']}; font-size: 10pt; line-height: 1.35; }}
        QLabel#comparisonStep, QLabel#comparisonStepReady {{ border-radius: 8px; padding: 10px 12px; font-weight: 600; }}
        QLabel#comparisonStep {{ color: {COLORS['muted']}; background: #F1F4F9; }}
        QLabel#comparisonStepReady {{ color: {COLORS['primary']}; background: #E6EEFF; }}
        QLabel#fileTypeBadge {{ color: #FFFFFF; background: #217346; border-radius: 5px; padding: 4px 7px; font-size: 8pt; font-weight: 800; }}
        QLabel#sourceCardTitle {{ color: {COLORS['primary']}; font-size: 13pt; font-weight: 700; }}
        QLabel#sourceFileName {{ color: {COLORS['text']}; font-weight: 700; }}
        QLabel#sourceFileLocation, QLabel#sourceContextText {{ color: {COLORS['muted']}; font-size: 9pt; }}
        QLabel#processingSourceStrip {{ color: {COLORS['muted']}; background: #F5F7FB; border-radius: 7px; padding: 8px 10px; }}
        QLabel#processingElapsed {{ color: {COLORS['primary']}; background: #E6EEFF; border-radius: 8px; padding: 6px 9px; font-size: 10pt; font-weight: 700; }}
        QLabel#fileStatusPending, QLabel#fileStatusReady {{ border-radius: 8px; padding: 4px 8px; font-size: 9pt; font-weight: 700; }}
        QLabel#fileStatusPending {{ color: {COLORS['muted']}; background: #EFF2F7; }}
        QLabel#fileStatusReady {{ color: {COLORS['success']}; background: #EAF8F0; }}
        QLabel#processingStep, QLabel#processingStepActive, QLabel#processingStepDone {{ padding: 7px 0; }}
        QLabel#processingStep {{ color: {COLORS['muted']}; }}
        QLabel#processingStepActive {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#processingStepDone {{ color: {COLORS['success']}; font-weight: 600; }}
        QLabel#processingStepPending {{ color: {COLORS['muted']}; background: #EFF2F7; border-radius: 8px; padding: 4px 8px; font-size: 9pt; font-weight: 700; }}
        QLabel#contextTitle {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#fileContextChip {{ color: {COLORS['text']}; background: #FFFFFF; border: 1px solid #DCE4F1; border-radius: 7px; padding: 5px 8px; }}
        QLabel#contextMetric {{ color: {COLORS['primary']}; font-weight: 700; }}
        QLabel#summaryLabel {{ color: {COLORS['text']}; padding: 4px 2px; }}
        QLabel#activityPending, QLabel#activityReady, QLabel#activityRunning, QLabel#activitySuccess, QLabel#activityWarning {{ border-radius: 9px; padding: 5px 9px; font-size: 9pt; font-weight: 700; }}
        QLabel#activityPending {{ color: {COLORS['muted']}; background: #EFF2F7; }}
        QLabel#activityReady, QLabel#activityRunning {{ color: {COLORS['primary']}; background: #E6EEFF; }}
        QLabel#activitySuccess {{ color: {COLORS['success']}; background: #EAF8F0; }}
        QLabel#activityWarning {{ color: {COLORS['warning']}; background: #FFF4E5; }}
        QLabel#statusInfo {{ color: {COLORS['primary']}; background: {COLORS['info_surface']}; border-radius: 6px; padding: 9px; }}
        QLabel#statusSuccess {{ color: {COLORS['success']}; background: #ECFDF3; border-radius: 6px; padding: 9px; }}
        QLabel#statusWarning {{ color: {COLORS['warning']}; background: #FFF7ED; border-radius: 6px; padding: 9px; }}
        QTableWidget[dropActive="true"] {{ background: #E6EEFF; border: 2px dashed {COLORS['focus']}; }}
        QScrollBar:vertical {{ background: transparent; width: 12px; margin: 6px 2px; }}
        QScrollBar::handle:vertical {{ background: #B8C5DC; min-height: 36px; border: 3px solid transparent; border-radius: 5px; background-clip: padding; }}
        QScrollBar::handle:vertical:hover {{ background: #7F96BD; }}
        QScrollBar::handle:vertical:pressed {{ background: {COLORS['primary']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 6px; }}
        QScrollBar::handle:horizontal {{ background: #B8C5DC; min-width: 36px; border: 3px solid transparent; border-radius: 5px; background-clip: padding; }}
        QScrollBar::handle:horizontal:hover {{ background: #7F96BD; }}
        QScrollBar::handle:horizontal:pressed {{ background: {COLORS['primary']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal, QScrollBar::corner {{ background: transparent; }}
    """)
