"""Complete portable snapshots, malformed input, and real asynchronous UI flow."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from dataclasses import replace
from unittest.mock import patch
import zipfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QSettings, Qt, QMimeData, QUrl, QPoint, QPointF
from PySide6.QtGui import QFontDatabase, QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from core.models import ComparatorResult, ComparatorIncident
from services.comparador_tempo_service import ComparadorTempoService, TIME_COLUMNS
from services.comparison_archive import save_archive, load_archive
from ui.pages.comparador_tempo_page import ComparadorTempoPage
from ui.pages.home_page import HomePage
from ui.theme import apply_application_style
from ui.widgets.comparison_review import calculation_text, comparison_triplet, matches_reason
from test_comparison_review import example_row


def fixture(directory):
    row = replace(example_row(), red_fields=('ABSENT',),
                  incidence_messages=('Falta fichaje de salida',),
                  suppressed_fields=('HFJ (15%)', 'BOLSA (X%)', 'NOCTUR'),
                  pm_source_minutes={**example_row().pm_source_minutes, 'ABSENT':60},
                  tempo_source_minutes={**example_row().tempo_source_minutes, '1052-HDESC':60})
    missing = replace(example_row('ML', '200', 'OTRO APELLIDO NOMBRE'), missing_source='Tempo',
                      trigger_fields=(), red_fields=(), incidence_messages=('No aparece en Tempo',),
                      suppressed_fields=('Trab. Día Tempo', 'Control', *TIME_COLUMNS))
    rows=[]
    for item in (row, missing):
        snapshots={field:{'explanation':calculation_text(item,field), 'triplet':list(comparison_triplet(item,field))}
                   for field in ('Trab. Día Tempo','Control',*TIME_COLUMNS)}
        rows.append(replace(item, review_snapshot=snapshots))
    incident=ComparatorIncident('Absentismo','TR','100',row.worker,row.worker,'ABSENT',60,60,0,'Revisión',row.pm_source_minutes,row.tempo_source_minutes)
    result=ComparatorResult(directory/'result.xlsx',directory/'incidents.xlsx',tuple(rows),(incident,),('ML','TR'),12.5,
                            ('Ruta privada C:/Usuarios/persona/confidencial.xlsx',),{'TR':{'pm':4,'tempo':3},'ML':{'pm':2,'tempo':1}})
    service=ComparadorTempoService()
    service._save_main_workbook(result.output_path,result.rows,result.section_counts)
    service._save_incidents_workbook(result.incidents_path,result.incidents)
    return result


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.result=fixture(self.root)
        self.path=self.root/'comparison.rrhh'
        save_archive(self.path,self.result)

    def test_full_roundtrip_preserves_every_value_and_report(self):
        imported=load_archive(self.path)
        self.assertEqual(imported.result.rows,self.result.rows)
        self.assertEqual(imported.result.incidents,self.result.incidents)
        self.assertEqual(imported.result.section_counts,self.result.section_counts)
        self.assertEqual(imported.reports['resultado.xlsx'],self.result.output_path.read_bytes())
        self.assertEqual(imported.reports['incidencias.xlsx'],self.result.incidents_path.read_bytes())
        self.assertEqual(imported.result.detail_lines,())
        with zipfile.ZipFile(self.path) as archive:
            self.assertNotIn(str(self.root),archive.read('result.json').decode())
            self.assertNotIn('confidencial',archive.read('result.json').decode())
        for original,restored in zip(self.result.rows,imported.result.rows):
            for field in ('Trab. Día Tempo','Control',*TIME_COLUMNS):
                self.assertEqual(calculation_text(original,field),calculation_text(restored,field))
                self.assertEqual(comparison_triplet(original,field),comparison_triplet(restored,field))
            for reason in ('','Control','red','marking','only_pm','only_tempo',*TIME_COLUMNS):
                self.assertEqual(matches_reason(original,reason),matches_reason(restored,reason))

    def test_legacy_control_explanation_is_not_reinterpreted_on_import(self):
        original = self.result.rows[0]
        old_control = {'explanation': 'Tempo · Trab. Dia: 10:00; PM · RUIDO: 8:00; +2:00',
                       'triplet': ['10:00', '8:00', '+2:00', 'Diferencia']}
        row = replace(original, sap_daily_minus_noise_minutes=120,
                      review_snapshot={**original.review_snapshot, 'Control': old_control})
        result = replace(self.result, rows=(row,))
        save_archive(self.path, result, app_version='1.0.21')
        restored = load_archive(self.path)
        self.assertEqual(restored.app_version, '1.0.21')
        self.assertEqual(restored.result.rows[0].sap_daily_minus_noise_minutes, 120)
        self.assertEqual(calculation_text(restored.result.rows[0], 'Control'), old_control['explanation'])
        self.assertEqual(comparison_triplet(restored.result.rows[0], 'Control'), tuple(old_control['triplet']))

    def rewrite(self, mutate, *, hash_result=True):
        with zipfile.ZipFile(self.path) as archive:
            parts={name:archive.read(name) for name in archive.namelist()}
        mutate(parts)
        if hash_result:
            manifest=json.loads(parts['manifest.json'])
            manifest['hashes']={name:hashlib.sha256(content).hexdigest() for name,content in parts.items() if name!='manifest.json'}
            parts['manifest.json']=json.dumps(manifest).encode()
        out=self.root/'malformed.rrhh'
        with zipfile.ZipFile(out,'w') as archive:
            for name,content in parts.items(): archive.writestr(name,content)
        return out

    def test_reject_corruption_unknown_schema_paths_and_invalid_types(self):
        def corrupt(parts): parts['result.json']+=b' '
        with self.assertRaises(ValueError): load_archive(self.rewrite(corrupt,hash_result=False))
        def schema(parts):
            manifest=json.loads(parts['manifest.json']); manifest['schema']=999
            parts['manifest.json']=json.dumps(manifest).encode()
        with self.assertRaisesRegex(ValueError,'compatible'): load_archive(self.rewrite(schema))
        with self.assertRaises(ValueError): load_archive(self.rewrite(lambda parts: parts.update({'../escape':'x'.encode()})))
        for invalid in ('0:30',True,None,10**20):
            def badtype(parts):
                data=json.loads(parts['result.json']); data['rows'][0]['values_minutes']['ABSENT']=invalid
                parts['result.json']=json.dumps(data).encode()
            with self.subTest(value=invalid), self.assertRaises(ValueError): load_archive(self.rewrite(badtype))

    def test_reexport_does_not_need_originals_or_change_provenance(self):
        imported=load_archive(self.path)
        self.result.output_path.unlink(); self.result.incidents_path.unlink()
        again=self.root/'again.rrhh'
        with patch.object(ComparadorTempoService,'run',side_effect=AssertionError('No recalculation')):
            save_archive(again,imported.result,reports=imported.reports,created_at=imported.created_at,app_version=imported.app_version)
            restored=load_archive(again)
        self.assertEqual(restored,imported)

    def test_atomic_failure_preserves_previous_archive(self):
        before=self.path.read_bytes()
        with patch('services.comparison_archive.os.replace',side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError): save_archive(self.path,self.result)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(list(self.root.glob('.rrhh-*.tmp')))

    def test_snapshot_text_survives_later_presentation_rule_changes(self):
        imported=load_archive(self.path)
        with patch('ui.widgets.comparison_review.SAP_FIELD_BY_TEMPO',{}):
            for row in imported.result.rows:
                for concept,snapshot in row.review_snapshot.items():
                    self.assertEqual(calculation_text(row,concept),snapshot['explanation'])
                    self.assertEqual(comparison_triplet(row,concept),tuple(snapshot['triplet']))

    def test_reject_oversize_empty_non_object_and_unsafe_report(self):
        with patch('services.comparison_archive.MAX_BYTES',10):
            with self.assertRaises(ValueError): load_archive(self.path)
        with self.assertRaises(ValueError): load_archive(self.rewrite(lambda p:p.update({'manifest.json':b'[]'}), hash_result=False))
        def unsafe(parts):
            buffer=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(parts['resultado.xlsx'])) as source, zipfile.ZipFile(buffer,'w') as target:
                for name in source.namelist(): target.writestr(name,source.read(name))
                target.writestr('xl/vbaProject.bin',b'not allowed')
            parts['resultado.xlsx']=buffer.getvalue()
        with self.assertRaises(ValueError): load_archive(self.rewrite(unsafe))


class SharingUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for filename in ('segoeui.ttf', 'segoeuib.ttf'):
            QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts')/filename))
        apply_application_style(cls.app)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.page=ComparadorTempoPage(settings=QSettings(str(self.root/'settings.ini'),QSettings.IniFormat))
        self.page.resize(1920,1000); self.page.show(); self.app.processEvents()

    def tearDown(self):
        self.page.close(); self.page.deleteLater(); self.app.processEvents(); self.temp.cleanup()

    def wait_transfer(self):
        deadline=time.monotonic()+15
        while self.page.is_running and time.monotonic()<deadline:
            QTest.qWait(20)
        self.assertFalse(self.page.is_running)

    def test_export_filters_import_and_new_comparison_without_recalculation(self):
        result=fixture(self.root)
        self.page._on_success(result)
        self.page.section_filter.setCurrentText('TR')
        self.assertEqual(len(self.page._preview_rows),1)
        destination=self.root/'shared.rrhh'
        with patch.object(ComparadorTempoService,'run',side_effect=AssertionError('No recalculation')), \
             patch('ui.pages.comparador_tempo_page.QMessageBox.question',return_value=QMessageBox.Yes), \
             patch('ui.pages.comparador_tempo_page.QMessageBox.information'), \
             patch('ui.pages.comparador_tempo_page.QMessageBox.warning') as warning, \
             patch('ui.pages.comparador_tempo_page.QFileDialog.getSaveFileName',return_value=(str(destination),'')):
            self.page._choose_export(); self.wait_transfer()
            warning.assert_not_called()
            self.assertEqual(len(load_archive(destination).result.rows),2)
            self.page._remember_directory('output',self.root)
            result.output_path.unlink(); result.incidents_path.unlink()
            self.page._import_comparison(destination); self.wait_transfer()
            warning.assert_not_called()
            self.assertEqual(len(self.page._preview_rows),2)
            self.assertTrue(self.page.imported_label.isVisible())
            self.assertFalse(self.page.sources_action.isEnabled())
            self.assertEqual(self.page._last_directory('output'),str(self.root))
            self.page.reason_filter.setCurrentIndex(self.page.reason_filter.findData('ABSENT'))
            self.assertEqual(len(self.page._preview_rows),1)
            self.page._open_worker_detail()
            self.assertIn('ABSENT',self.page.worker_detail.browser.toPlainText())
            self.assertEqual(self.page.open_result_button.text(),'Guardar resultado')
            copy_path=self.root/'copied.xlsx'
            with patch('ui.pages.comparador_tempo_page.QFileDialog.getSaveFileName',return_value=(str(copy_path),'')):
                self.page._open_result(); self.wait_transfer()
            self.assertEqual(copy_path.read_bytes(),load_archive(destination).reports['resultado.xlsx'])
            folder=os.environ.get('RRHH_HOME_CAPTURE')
            if folder:
                self.page.grab().save(str(Path(folder)/'imported-review.png'))
            self.page.new_comparison_button.click()
            self.assertIsNone(self.page._imported_archive)
            self.assertTrue(destination.exists())

    def test_invalid_import_preserves_current_result_and_drop_routes_archive(self):
        result=fixture(self.root)
        self.page._on_success(result)
        invalid=self.root/'invalid.rrhh'; invalid.touch()
        with patch('ui.pages.comparador_tempo_page.QMessageBox.question',return_value=QMessageBox.Yes), \
             patch('ui.pages.comparador_tempo_page.QMessageBox.warning') as warning:
            self.page._import_comparison(invalid); self.wait_transfer()
            warning.assert_called_once()
        self.assertIs(self.page._last_result,result)
        mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(invalid))])
        enter=QDragEnterEvent(QPoint(10,10),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        self.page.dragEnterEvent(enter); self.assertTrue(enter.isAccepted())
        drop=QDropEvent(QPointF(10,10),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        with patch.object(self.page,'_import_comparison') as receive:
            self.page.dropEvent(drop)
            receive.assert_called_once_with(invalid)

    def test_home_navigation_and_manual_update_cleanup(self):
        from ui.main_window import MainWindow
        from services.update_service import UpdateInfo
        with patch('ui.main_window.UpdateService.is_installed_copy',return_value=False):
            window=MainWindow(); window.show(); self.app.processEvents()
            try:
                self.assertTrue(window.home_action.isChecked())
                window.home_page.comparator_card.open_button.click()
                self.assertIs(window.stack.currentWidget(),window.comparador_page)
                self.assertTrue(window.comparador_action.isChecked())
                window.home_action.trigger()
                self.assertTrue(window.home_action.isChecked())
                for value in (None, UpdateInfo('99.0','https://example.invalid','0'*64)):
                    with patch('workers.update_worker.UpdateService.check_for_update',return_value=value), \
                         patch('ui.main_window.QMessageBox.information'), \
                         patch('ui.main_window.UpdateService.launch_updater') as launch:
                        window.home_page.updates_button.click()
                        deadline=time.monotonic()+5
                        while window._update_thread is not None and time.monotonic()<deadline: QTest.qWait(20)
                        self.assertIsNone(window._update_thread)
                        self.assertTrue(window.home_page.updates_button.isEnabled())
                        launch.assert_not_called()
                with patch('workers.update_worker.UpdateService.check_for_update',side_effect=OSError('Sin conexión')):
                    window.home_page.updates_button.click()
                    deadline=time.monotonic()+5
                    while window._update_thread is not None and time.monotonic()<deadline: QTest.qWait(20)
                    self.assertIn('No se pudo',window.home_page.update_status.text())
            finally:
                window.close(); window.deleteLater(); self.app.processEvents()

    def test_home_vertical_cards_and_responsive_capture(self):
        home=HomePage(); home.show()
        try:
            # Exercise both directions: old column minima only failed after shrinking.
            for width,height in ((1920,1000),(1600,900),(1280,720),(1100,720),
                                 (900,620),(1280,720),(1920,1000),(2560,1080)):
                home.resize(width,height)
                QTest.qWait(30)
                self.assertLess(home.control_card.geometry().bottom(),home.comparator_card.y())
                self.assertEqual(home.width(),width)
                self.assertLessEqual(home.scroll.widget().width(),home.scroll.viewport().width())
                self.assertEqual(home.scroll.horizontalScrollBar().maximum(),0)
                self.assertLessEqual(home.content.width(),1480)
                if width>=1920:
                    self.assertEqual(home.scroll.verticalScrollBar().maximum(),0)
                    self.assertLess(home.control_card.height(),230)
                for card in (home.control_card,home.comparator_card):
                    self.assertTrue(card.open_button.isVisible())
                    self.assertGreaterEqual(card.open_button.height(),35)
                    self.assertLess(card.actions.geometry().right(),card.width())
                    self.assertLess(card.summary.geometry().bottom(),card.height())
                    for column in range(3):
                        self.assertEqual(card.grid.columnMinimumWidth(column),0)
                folder=os.environ.get('RRHH_HOME_CAPTURE')
                if folder:
                    Path(folder).mkdir(parents=True,exist_ok=True)
                    home.grab().save(str(Path(folder)/f'home-{width}.png'))
            controls=(home.control_card.open_button,home.control_card.guide_button,
                      home.comparator_card.open_button,home.comparator_card.guide_button,
                      home.help_button,home.news_button,home.updates_button)
            controls[0].setFocus()
            for first,second in zip(controls,controls[1:]):
                QTest.keyClick(first,Qt.Key_Tab)
                self.assertIs(self.app.focusWidget(),second)
        finally:
            home.close(); home.deleteLater()
