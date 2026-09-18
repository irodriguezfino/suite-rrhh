"""Reusable, view-only duration and multi-section filters."""

import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QToolButton,
    QVBoxLayout, QWidget, QWidgetAction,
)


class DurationFilter(QLineEdit):
    """Store minutes, display unbounded hours (not a time of day)."""

    valueChanged = Signal(int)
    HELP = ("Horas:minutos: 0:05 = cinco minutos; 1:30 = noventa minutos. "
            "También puedes escribir solo minutos. 0:00 elimina la tolerancia. "
            "Se aplica al dejar de escribir. Solo cambia la vista; conserva avisos especiales.")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minutes = 0
        self._select_on_release = False
        self.setObjectName("reviewTolerance")
        self.setAccessibleName("Tolerancia en horas y minutos, solo para la vista")
        self.setMinimumWidth(120)
        self.setMaximumWidth(140)
        self.setMaxLength(12)
        self.setText("0:00")
        self.setToolTip(self.HELP)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._apply)
        self.textEdited.connect(lambda _: self._timer.start())
        self.editingFinished.connect(self._finish)

    @staticmethod
    def parse(text):
        text = text.strip()
        if not text:
            return 0
        if re.fullmatch(r"[0-9]{1,6}", text):
            value = int(text)
        elif re.fullmatch(r"[0-9]{1,5}:[0-5]?[0-9]", text):
            hours, minutes = map(int, text.split(":"))
            value = hours * 60 + minutes
        else:
            return None
        return value if value <= 999999 else None

    def value(self):
        return self._minutes

    def setValue(self, minutes):
        minutes = max(0, min(999999, int(minutes)))
        self._timer.stop()
        changed = minutes != self._minutes
        self._minutes = minutes
        self.setText(f"{minutes // 60}:{minutes % 60:02d}")
        self._set_invalid(False)
        if changed:
            self.valueChanged.emit(minutes)

    def _set_invalid(self, invalid):
        message = ("Formato no válido. Usa horas:minutos (por ejemplo, 0:05). "
                   "Se mantiene la última tolerancia aplicada: "
                   f"{self._minutes // 60}:{self._minutes % 60:02d}." if invalid else self.HELP)
        self.setToolTip(message)
        self.setAccessibleDescription(message)
        if self.property("invalid") != invalid:
            self.setProperty("invalid", invalid)
            self.style().unpolish(self)
            self.style().polish(self)

    def _apply(self):
        minutes = self.parse(self.text())
        self._set_invalid(minutes is None)
        if minutes is not None and minutes != self._minutes:
            self._minutes = minutes
            self.valueChanged.emit(minutes)
        return minutes is not None

    def _finish(self):
        self._timer.stop()
        if self._apply():
            self.setValue(self._minutes)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._select_on_release = event.reason() == Qt.MouseFocusReason
        self.selectAll()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._select_on_release:
            self._select_on_release = False
            self.selectAll()


class SectionFilter(QToolButton):
    """Checkbox popup; an empty selection means all sections, not zero rows."""

    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = set()
        self._updating = False
        self.setProperty("reviewMenuButton", True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Filtrar por una o varias secciones")
        self.setMinimumWidth(150)
        self.setMaximumWidth(210)
        self.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        panel = QWidget(menu)
        layout = QVBoxLayout(panel)
        label = QLabel("Marca una o varias secciones")
        layout.addWidget(label)
        self.options = QListWidget()
        self.options.setAccessibleName("Secciones: usa Espacio para marcar o desmarcar")
        self.options.setMinimumWidth(300)
        layout.addWidget(self.options)
        hint = QLabel("Sin selección: todas · Esc cierra")
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)
        action = QWidgetAction(menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        menu.aboutToShow.connect(self.options.setFocus)
        self.setMenu(menu)
        self.options.itemChanged.connect(self._item_changed)
        self.set_options([])

    def set_options(self, options):
        self._updating = True
        self.options.clear()
        for title, value in [("Todas las secciones", None), *options]:
            item = QListWidgetItem(title, self.options)
            item.setData(Qt.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
        self.options.setFixedHeight(min(350, max(90, self.options.sizeHintForRow(0) * self.options.count() + 8)))
        self.options.setCurrentRow(0)
        self._updating = False
        self.set_selected(set())

    def selected_values(self):
        return set(self._selected)

    def selection_text(self):
        return ", ".join(self.options.item(i).text() for i in range(1, self.options.count())
                         if self.options.item(i).data(Qt.UserRole) in self._selected)

    def set_selected(self, values):
        allowed = {self.options.item(i).data(Qt.UserRole) for i in range(1, self.options.count())}
        selected = set(values) & allowed
        changed = selected != self._selected
        self._selected = selected
        self._updating = True
        for i in range(self.options.count()):
            item = self.options.item(i)
            checked = (not selected) if i == 0 else item.data(Qt.UserRole) in selected
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._updating = False
        title = ("Todas las secciones" if not selected else
                 self.selection_text() if len(selected) == 1 else f"{len(selected)} secciones")
        self.setText(title)
        self.setToolTip((self.selection_text() or "Todas las secciones") + "\nMarca varias casillas; se incluyen las filas de cualquiera de ellas.")
        self.setAccessibleDescription(self.toolTip())
        if changed:
            self.selectionChanged.emit()

    def _item_changed(self, item):
        if self._updating:
            return
        value = item.data(Qt.UserRole)
        selected = self.selected_values()
        if value is None:
            selected.clear()
        elif item.checkState() == Qt.Checked:
            selected.add(value)
        else:
            selected.discard(value)
        self.set_selected(selected)
