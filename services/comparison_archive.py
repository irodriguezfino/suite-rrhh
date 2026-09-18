"""Portable, versioned snapshots for read-only review; never run the comparator.

Only explicit known ZIP members are read. No paths from the sender are used.
SHA256 detects damage, not sender authenticity. This format is not encrypted.
"""
from dataclasses import dataclass, replace, fields
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

from core.app_info import APP_VERSION
from core.models import ComparatorRow, ComparatorIncident, ComparatorResult
from services.comparison_codec import result_to_payload, result_from_payload

FORMAT = 'suite-rrhh-comparison'
SCHEMA = 1
MAX_BYTES = 40 * 1024 * 1024
MAX_ROWS = 20000
MAX_INCIDENTS = 200000
CONCEPTS = {'Control', 'H. EXTRAS', 'HFJ (15%)', 'BOLSA (X%)', 'NOCTUR', 'PENOS', 'RUIDO', 'ABSENT'}
MEMBERS = {'manifest.json', 'result.json', 'resultado.xlsx', 'incidencias.xlsx'}


@dataclass(frozen=True)
class ComparisonArchive:
    result: ComparatorResult
    created_at: str
    app_version: str
    reports: dict[str, bytes]


def _require(condition, message='El archivo de comparación contiene datos no válidos.'):
    if not condition:
        raise ValueError(message)


def _text(value):
    _require(isinstance(value, str) and len(value) <= 12000)


def _minutes(value):
    _require(type(value) is int and abs(value) <= 10**9)


def _map(value):
    _require(isinstance(value, dict) and len(value) <= 32)
    for key, number in value.items():
        _text(key)
        _minutes(number)


def _strings(value, maximum=1000):
    _require(isinstance(value, list) and len(value) <= maximum)
    for item in value:
        _text(item)


def _validate(data):
    _require(isinstance(data, dict))
    _require(isinstance(data.get('rows'), list) and len(data['rows']) <= MAX_ROWS)
    _require(isinstance(data.get('incidents'), list) and len(data['incidents']) <= MAX_INCIDENTS)
    row_keys = {f.name for f in fields(ComparatorRow)}
    incident_keys = {f.name for f in fields(ComparatorIncident)}
    for row in data['rows']:
        _require(isinstance(row, dict) and set(row) == row_keys)
        for key in ('section', 'sap_code', 'worker', 'missing_source'):
            _text(row[key])
        _require(row['missing_source'] in {'', 'Tempo', 'Partes Mensuales'})
        for key in ('values_minutes', 'pm_source_minutes', 'tempo_source_minutes'):
            _map(row[key])
        _require(set(row['values_minutes']) <= CONCEPTS)
        for key in ('trigger_fields', 'red_fields', 'suppressed_fields', 'incidence_messages'):
            _strings(row[key])
        for key in ('trigger_fields', 'red_fields', 'suppressed_fields'):
            _require(set(row[key]) <= CONCEPTS | {'Trab. Día Tempo'})
        for key in ('sap_daily_work_minutes', 'sap_daily_minus_noise_minutes'):
            if row[key] is not None:
                _minutes(row[key])
        snapshots = row['review_snapshot']
        _require(isinstance(snapshots, dict) and set(snapshots) == CONCEPTS | {'Trab. Día Tempo'})
        for snapshot in snapshots.values():
            _require(isinstance(snapshot, dict) and set(snapshot) == {'explanation', 'triplet'})
            _text(snapshot['explanation'])
            _strings(snapshot['triplet'], 4)
            _require(len(snapshot['triplet']) == 4)
    for incident in data['incidents']:
        _require(isinstance(incident, dict) and set(incident) == incident_keys)
        for key, value in incident.items():
            if key in {'tempo_values_minutes', 'sap_values_minutes'}:
                _map(value)
            elif key in {'tempo_minutes', 'sap_minutes', 'difference_minutes'}:
                if value is not None:
                    _minutes(value)
            else:
                _text(value)
    _strings(data.get('sections'), 2000)
    _require(data.get('detail_lines') == [])  # Never transfer diagnostic paths.
    _require(data.get('output_path') == 'resultado.xlsx' and data.get('incidents_path') == 'incidencias.xlsx')
    _require(type(data.get('elapsed_seconds')) in (int, float) and math.isfinite(data['elapsed_seconds']) and 0 <= data['elapsed_seconds'] < 10**8)
    counts = data.get('section_counts')
    _require(isinstance(counts, dict) and len(counts) <= 2000)
    for section, count in counts.items():
        _text(section)
        _require(isinstance(count, dict) and set(count) == {'pm', 'tempo'})
        for value in count.values():
            _minutes(value)
            _require(value >= 0)


def _check_report(content):
    """Accept only inert XLSX report parts, never embedded code/external links."""
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        infos = workbook.infolist()
        _require(len(infos) <= 2000 and sum(i.file_size for i in infos) <= MAX_BYTES)
        names = {i.filename for i in infos}
        _require('[Content_Types].xml' in names and 'xl/workbook.xml' in names)
        for name in names:
            _require(not name.startswith(('/', '\\')) and '..' not in name.replace('\\', '/').split('/'))
            _require(not any(word in name.lower() for word in ('vbaproject', 'externallinks', 'embeddings', 'activex', 'customui')))


def save_archive(path: Path, result: ComparatorResult, *, reports=None, created_at=None, app_version=None):
    data = result_to_payload(replace(result, output_path=Path('resultado.xlsx'), incidents_path=Path('incidencias.xlsx'), detail_lines=()))
    # Normalize dataclass tuples to JSON arrays before validating.
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
    _validate(json.loads(encoded))
    contents = {'result.json': encoded}
    if reports is None:
        reports = {}
        for name, source in (('resultado.xlsx', result.output_path), ('incidencias.xlsx', result.incidents_path)):
            _require(source.is_file(), 'No se encuentra uno de los informes. Vuelve a generar la comparación antes de exportarla.')
            _require(source.stat().st_size <= MAX_BYTES, 'El informe es demasiado grande para este formato.')
            reports[name] = source.read_bytes()
    _require(set(reports) == {'resultado.xlsx', 'incidencias.xlsx'})
    for name, content in reports.items():
        _check_report(content)
        contents[name] = content
    manifest = dict(format=FORMAT, schema=SCHEMA, scope='complete',
                    created_at=created_at or datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    app_version=app_version or APP_VERSION,
                    hashes={name: hashlib.sha256(content).hexdigest() for name, content in contents.items()})
    contents['manifest.json'] = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
    _require(sum(map(len, contents.values())) <= MAX_BYTES, 'La comparación supera el límite de 40 MB.')
    fd, temporary = tempfile.mkstemp(prefix='.rrhh-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, content in contents.items():
                    archive.writestr(name, content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def load_archive(path: Path) -> ComparisonArchive:
    _require(path.stat().st_size <= MAX_BYTES, 'El archivo supera el límite de 40 MB.')
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            _require(len(infos) == len(MEMBERS) and {i.filename for i in infos} == MEMBERS,
                     'No es un archivo de comparación completo de Suite RRHH.')
            _require(sum(i.file_size for i in infos) <= MAX_BYTES)
            _require(all(not i.flag_bits & 1 for i in infos))
            manifest = json.loads(archive.read('manifest.json'))
            _require(isinstance(manifest, dict))
            _require(manifest.get('format') == FORMAT and manifest.get('scope') == 'complete')
            _require(type(manifest.get('schema')) is int and manifest['schema'] == SCHEMA, 'Formato de comparación no compatible. Actualiza Suite RRHH.')
            _text(manifest.get('created_at'))
            datetime.fromisoformat(manifest['created_at'])
            _text(manifest.get('app_version'))
            contents = {name: archive.read(name) for name in MEMBERS - {'manifest.json'}}
            _require(manifest.get('hashes') == {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()},
                     'El archivo está dañado o ha sido modificado. Solicita una nueva exportación.')
            data = json.loads(contents.pop('result.json'))
            _validate(data)
            for report in contents.values():
                _check_report(report)
            return ComparisonArchive(result_from_payload(data), manifest['created_at'], manifest['app_version'], contents)
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('No se puede abrir esta comparación. Solicita al remitente que vuelva a exportarla.') from exc
