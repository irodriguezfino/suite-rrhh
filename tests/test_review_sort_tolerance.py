"""View-only sorting and tolerance: values, identity and shared results stay intact."""
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from core.models import ComparatorResult, ComparatorRow
from services.comparador_tempo_service import TIME_COLUMNS
from services.comparison_archive import load_archive
from ui.pages.comparador_tempo_page import ComparadorTempoPage
from ui.theme import apply_application_style
from ui.widgets.comparison_review import matches_tolerance, sorted_review_rows, review_column_value
from ui.widgets.review_filters import DurationFilter
from test_comparison_archive import fixture


def row(code, minutes, section='TR', name=None, **kwargs):
    return ComparatorRow(section, str(code), name or f'APELLIDO {code}',
                         dict.fromkeys(TIME_COLUMNS, 0), trigger_fields=('Control',),
                         sap_daily_work_minutes=480, sap_daily_minus_noise_minutes=minutes, **kwargs)


class ToleranceLogicTests(unittest.TestCase):
    def test_duration_format_and_invalid_values(self):
        for text, expected in [('0:00',0),('0:05',5),('1:30',90),('25:05',1505),
                               ('5',5),('1:5',65),('',0),(' 0:05 ',5),
                               ('0:60',None),('-0:05',None),('abc',None),
                               ('1:',None),('9999999',None),('99999:59',None)]:
            self.assertEqual(DurationFilter.parse(text),expected,text)

    def test_inclusive_boundary_and_negative_values(self):
        for value in (-6, -5, -4, 0, 4, 5, 6):
            with self.subTest(value=value):
                self.assertEqual(matches_tolerance(row(100, value), 5), abs(value) > 5)
                self.assertTrue(matches_tolerance(row(100, value), 0))

    def test_special_alerts_and_missing_workers_are_not_hidden(self):
        for changes in ({'red_fields': ('ABSENT',)}, {'red_fields': ('RUIDO',)},
                        {'red_fields': ('NOCTUR',)}, {'missing_source': 'Tempo'},
                        {'missing_source': 'Partes Mensuales'},
                        {'incidence_messages': ('Falta fichaje de salida',)},
                        {'incidence_messages': ('Falta fichaje de entrada',)},
                        {'incidence_messages': ('Sección pendiente de verificar',)}):
            self.assertTrue(matches_tolerance(row(100, 2, **changes), 5), changes)
        self.assertFalse(matches_tolerance(row(100, 2, incidence_messages=('Vacaciones',)), 5))

    def test_tolerance_is_applied_to_selected_reason(self):
        item = replace(row(100, 3), trigger_fields=('Control', 'PENOS'),
                       values_minutes={**dict.fromkeys(TIME_COLUMNS, 0), 'PENOS': 20})
        self.assertTrue(matches_tolerance(item, 5))
        self.assertFalse(matches_tolerance(item, 5, 'Control'))
        self.assertTrue(matches_tolerance(item, 5, 'PENOS'))
        self.assertTrue(matches_tolerance(replace(item, red_fields=('ABSENT',)), 5, 'ABSENT'))

    def test_sort_signed_minutes_numerically_and_nulls_last(self):
        rows = [row(10, 120), row(2, 600), row(3, -120), row(4, -600),
                row(5, 0), row(6, 0, suppressed_fields=('Control',)),
                row(7, None, missing_source='Tempo')]
        self.assertEqual([r.sap_code for r in sorted_review_rows(rows, 4)], ['4','3','5','10','2','6','7'])
        self.assertEqual([r.sap_code for r in sorted_review_rows(rows, 4, True)], ['2','10','5','3','4','6','7'])
        self.assertEqual([r.sap_code for r in sorted_review_rows(rows, 0)], ['2','3','4','5','6','7','10'])

    def test_every_column_and_stable_ties(self):
        a = row(2, 5, 'TR', 'ZETA')
        b = row(1, 5, 'ML', 'ÁLVAREZ')
        for col in range(13):
            self.assertEqual(len(sorted_review_rows([a,b], col)), 2)
            self.assertEqual(len(sorted_review_rows([a,b], col, True)), 2)
        for descending in (False, True):
            self.assertEqual(sorted_review_rows([a,b],4,descending), [b,a])
        self.assertIsNone(review_column_value(a,11))  # No ABSENT shown.
        self.assertEqual(review_column_value(replace(a, red_fields=('ABSENT',)),11),0)


class ReviewSortingUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for name in ('segoeui.ttf','segoeuib.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
        apply_application_style(cls.app)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.page=ComparadorTempoPage(settings=QSettings(str(self.root/'settings.ini'),QSettings.IniFormat))
        self.page.resize(1920,1000)
        self.page.show()
        self.app.processEvents()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def load(self, rows):
        result=ComparatorResult(self.root/'result.xlsx',self.root/'incidents.xlsx',tuple(rows),(),('ML','TR'),0,())
        self.page._on_success(result)
        self.app.processEvents()
        return result

    def click_header(self, column, frozen=False):
        header=(self.page.preview_table.frozen if frozen else self.page.preview_table).horizontalHeader()
        point=QPoint(header.sectionViewportPosition(column)+header.sectionSize(column)//2,header.height()//2)
        QTest.mouseClick(header.viewport(),Qt.LeftButton,pos=point)

    def test_header_clicks_sort_both_views_and_preserve_selected_detail(self):
        original=self.load([row(1,120,name='ZETA'),row(2,600,name='ALFA'),row(3,-30,'ML','BEA')])
        self.page.preview_table.setCurrentCell(1,4)
        self.page._open_worker_detail()
        selected=self.page._selected_review_row()
        self.click_header(4)
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['3','1','2'])
        self.click_header(4)
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['2','1','3'])
        self.assertEqual(self.page._selected_review_row(),selected)
        self.assertEqual(self.page.worker_detail._row,selected)
        for view in (self.page.preview_table,self.page.preview_table.frozen):
            self.assertEqual(view.horizontalHeader().sortIndicatorSection(),4)
            self.assertEqual(view.horizontalHeader().sortIndicatorOrder(),Qt.DescendingOrder)
        self.click_header(1,True)
        self.assertEqual([r.worker for r in self.page._preview_rows],['ALFA','BEA','ZETA'])
        for index,item in enumerate(self.page._preview_rows):
            self.assertEqual(self.page.preview_table.item(index,0).text(),item.sap_code)
        self.assertIs(self.page._last_result,original)
        self.page._reset_sort()
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['3','2','1'])

    def test_filter_reset_new_comparison_and_accessible_sorting(self):
        self.load([row(1,5),row(2,-5),row(3,6),row(4,-6),row(5,1,red_fields=('ABSENT',))])
        self.page.tolerance_filter.setFocus()
        QTest.keyClick(self.page.tolerance_filter,Qt.Key_A,Qt.ControlModifier)
        QTest.keyClicks(self.page.tolerance_filter,'5')
        QTest.keyClick(self.page.tolerance_filter,Qt.Key_Return)
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['3','4','5'])
        self.assertIn('5 min',self.page.active_filters.toolTip())
        self.page.reason_filter.setCurrentIndex(self.page.reason_filter.findData('Control'))
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['3','4'])
        self.page.accessible_action.setChecked(True)
        self.click_header(4)
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['4','3'])
        self.page._reset_preview_filters()
        self.assertEqual(self.page.tolerance_filter.value(),0)
        self.assertEqual(len(self.page._preview_rows),5)
        self.page._clear()
        self.assertIsNone(self.page._sort_column)
        self.assertEqual(self.page.tolerance_filter.value(),0)

    def test_export_keeps_complete_result_with_sort_and_tolerance(self):
        result=fixture(self.root)
        self.page._on_success(result)
        self.page.tolerance_filter.setValue(999)
        self.page.reason_filter.setCurrentIndex(self.page.reason_filter.findData('Control'))
        self.assertEqual(self.page._preview_rows, [])
        self.page._sort_preview(4)
        self.page._sort_preview(4)
        target=self.root/'complete.rrhh'
        with patch('ui.pages.comparador_tempo_page.QFileDialog.getSaveFileName',return_value=(str(target),'')), \
             patch('ui.pages.comparador_tempo_page.QMessageBox.question',return_value=QMessageBox.Yes), \
             patch('ui.pages.comparador_tempo_page.QMessageBox.information'), \
             patch('ui.pages.comparador_tempo_page.QMessageBox.warning') as warning:
            self.page._choose_export()
            for _ in range(200):
                if not self.page.is_running:break
                QTest.qWait(20)
            self.assertFalse(self.page.is_running)
            warning.assert_not_called()
        restored=load_archive(target)
        self.assertEqual(restored.result.rows,result.rows)
        self.assertEqual(restored.reports['resultado.xlsx'],result.output_path.read_bytes())
        self.page._show_imported(restored,target)
        self.page.tolerance_filter.setValue(5)
        self.page._sort_preview(4)
        self.assertIs(self.page._last_result,restored.result)

    def test_capture_and_large_preview(self):
        self.load([row(i,(-1 if i%2 else 1)*i*2) for i in range(1,31)])
        self.page.tolerance_filter.setValue(5)
        self.page._sort_preview(4)
        self.app.processEvents()
        self.assertGreaterEqual(self.page.review_splitter.height(),self.page.height()//2)
        folder=os.environ.get('RRHH_SORT_CAPTURE')
        for width,height in ((1920,1000),(1280,720),(900,620)):
            self.page.resize(width,height)
            QTest.qWait(40)
            self.assertTrue(self.page.tolerance_filter.isVisible())
            if folder:
                Path(folder).mkdir(parents=True,exist_ok=True)
                self.page.grab().save(str(Path(folder)/f'review-{width}.png'))

    def test_click_type_applies_without_enter_and_empty_results_keep_focus(self):
        self.load([row(1,3),row(2,6)])
        edit=self.page.tolerance_filter
        self.assertEqual(edit.text(),'0:00')
        self.page.worker_search.setFocus()
        QTest.mouseClick(edit,Qt.LeftButton,pos=QPoint(15,edit.height()//2))
        self.assertEqual(edit.selectedText(),'0:00')
        QTest.keyClicks(edit,'0:05')
        QTest.qWait(400)
        self.assertEqual(edit.value(),5)
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['2'])
        self.assertTrue(edit.hasFocus())
        QTest.keyClick(edit,Qt.Key_A,Qt.ControlModifier)
        QTest.keyClicks(edit,'1:30')
        QTest.qWait(400)
        self.assertEqual(edit.value(),90)
        self.assertFalse(self.page._preview_rows)
        self.assertTrue(edit.hasFocus())
        QTest.keyClick(edit,Qt.Key_A,Qt.ControlModifier)
        QTest.keyClicks(edit,'0:00')
        QTest.qWait(400)
        self.assertEqual(len(self.page._preview_rows),2)
        self.assertTrue(edit.hasFocus())

    def test_invalid_input_keeps_previous_filter_and_reset_cancels_debounce(self):
        self.load([row(1,3),row(2,8)])
        edit=self.page.tolerance_filter
        edit.setValue(5)
        edit.setFocus()
        QTest.keyClick(edit,Qt.Key_A,Qt.ControlModifier)
        QTest.keyClicks(edit,'0:99')
        QTest.qWait(400)
        self.assertEqual(edit.value(),5)
        self.assertTrue(edit.property('invalid'))
        self.assertIn('Formato no válido',edit.accessibleDescription())
        QTest.keyClick(edit,Qt.Key_A,Qt.ControlModifier)
        QTest.keyClicks(edit,'0:20')
        self.page._reset_preview_filters()
        QTest.qWait(400)
        self.assertEqual(edit.value(),0)
        self.assertEqual(edit.text(),'0:00')
        self.assertFalse(edit.property('invalid'))
        self.assertEqual(len(self.page._preview_rows),2)

    def test_multi_sections_counts_filters_and_overlap(self):
        rows=[row(1,3,'ML'),row(2,8,'TR'),row(3,9,'X'),
              row(4,0,'ML',missing_source='Tempo'),row(5,0,'',missing_source='Partes Mensuales')]
        result=replace(self.load(rows),sections=('ML','TR','X',''),
                       section_counts={'ML':{'pm':4,'tempo':3},'TR':{'pm':8,'tempo':7}})
        self.page._on_success(result)
        sections=self.page.section_filter
        sections.set_selected({'ML','TR'})
        self.assertEqual({r.sap_code for r in self.page._preview_rows},{'1','2','4'})
        self.assertIn('Partes Mensuales: 12 · Tempo: 10',self.page.source_count.text())
        self.assertEqual(sections.text(),'2 secciones')
        self.page.tolerance_filter.setValue(5)
        self.assertEqual({r.sap_code for r in self.page._preview_rows},{'2','4'})
        self.page.reason_filter.setCurrentIndex(self.page.reason_filter.findData('Control'))
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['2'])
        self.page._reset_preview_filters()
        sections.set_selected({'ML','__missing__'})
        self.assertEqual({r.sap_code for r in self.page._preview_rows},{'1','4','5'})
        self.assertEqual(len(self.page._preview_rows),3)
        self.assertIn('solo en un origen',self.page.source_count.text())
        sections.set_selected({'X'})
        self.assertEqual(self.page.source_count.text(),'Recuentos de origen no disponibles')
        sections.set_selected({''})
        self.assertEqual([r.sap_code for r in self.page._preview_rows],['5'])
        self.page._on_success(result)
        self.assertFalse(sections.selected_values())
        self.assertEqual(self.page.tolerance_filter.text(),'0:00')

    def test_sections_checkbox_mouse_and_keyboard_popup_stays_open(self):
        self.load([row(1,3,'ML'),row(2,8,'TR')])
        sections=self.page.section_filter
        menu=sections.menu()
        menu.popup(sections.mapToGlobal(QPoint(0,sections.height())))
        QTest.qWait(50)
        options=sections.options
        self.assertTrue(menu.isVisible())
        rect=options.visualItemRect(options.item(1))
        QTest.mouseClick(options.viewport(),Qt.LeftButton,pos=QPoint(rect.left()+10,rect.center().y()))
        self.assertEqual(sections.selected_values(),{'ML'})
        self.assertTrue(menu.isVisible())
        options.setCurrentRow(2)
        QTest.keyClick(options,Qt.Key_Space)
        self.assertEqual(sections.selected_values(),{'ML','TR'})
        self.assertTrue(menu.isVisible())
        options.setCurrentRow(0)
        QTest.keyClick(options,Qt.Key_Space)
        self.assertFalse(sections.selected_values())
        QTest.keyClick(options,Qt.Key_Escape)
        self.app.processEvents()
        self.assertFalse(menu.isVisible())
        sections.setFocus()
        keyboard_open=[]
        def inspect_keyboard_popup():
            keyboard_open.append(menu.isVisible() and options.hasFocus())
            folder=os.environ.get('RRHH_SORT_CAPTURE')
            if folder:
                menu.grab().save(str(Path(folder)/'section-popup.png'))
            menu.close()
        QTimer.singleShot(100,inspect_keyboard_popup)
        QTest.keyClick(sections,Qt.Key_Space)
        QTest.qWait(150)
        self.assertEqual(keyboard_open,[True])
