"""Shared data transport. No Excel access and no business calculations."""
from dataclasses import asdict
from pathlib import Path
from core.models import ComparatorResult, ComparatorRow, ComparatorIncident


def result_to_payload(result: ComparatorResult) -> dict:
    payload = asdict(result)
    payload['output_path'] = str(result.output_path)
    payload['incidents_path'] = str(result.incidents_path)
    return payload


def result_from_payload(data: dict) -> ComparatorResult:
    rows = []
    for item in data['rows']:
        values = dict(item)
        for key in ('trigger_fields', 'incidence_messages', 'suppressed_fields', 'red_fields'):
            values[key] = tuple(values.get(key, ()))
        rows.append(ComparatorRow(**values))
    return ComparatorResult(
        Path(data['output_path']), Path(data['incidents_path']), tuple(rows),
        tuple(ComparatorIncident(**item) for item in data['incidents']),
        tuple(data['sections']), data['elapsed_seconds'], tuple(data['detail_lines']),
        data.get('section_counts', {}),
    )
