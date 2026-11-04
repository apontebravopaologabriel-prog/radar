import io
import json
import subprocess
import sys
import zipfile
from unittest.mock import Mock

import pytest
from fpdf import FPDF

from radar import cv_import
from radar.db.database import connection
from radar.db.queries import get_profile
from radar.geolocation import LIMA_PLACES, infer_location
from radar.sources.computrabajo import ComputrabajoSource

TEXT = 'Ana Perez\nana@example.test\n+51 987654321\nFormación académica\nEstudiante de Ingeniería Industrial\nExperiencia laboral\nAnalista | ACME\n2023-01 - 2024-12\nHabilidades\nExcel y SQL'


def word(text):
    from xml.sax.saxutils import escape

    output = io.BytesIO()
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + ''.join('<w:p><w:r><w:t>'+escape(line)+'</w:t></w:r></w:p>' for line in text.splitlines()) + '</w:body></w:document>'
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return output.getvalue()


def draft():
    return cv_import.preview(word(TEXT), 'cv.docx', 'industrial_engineering')


def test_document_preview_is_local_and_does_not_modify_profile():
    result = draft()
    assert result['name'] == 'Ana Perez' and result['contact']['email'] == 'ana@example.test'
    assert result['education'][0]['status'] == 'estudiante'
    assert result['experience'][0]['from'] == '2023-01'
    assert 'Excel' in result['detected_skills'] and 'skills' not in result
    assert get_profile() is None


def test_pdf_extraction_and_empty_scan_error():
    pdf = FPDF(); pdf.add_page(); pdf.set_font('Helvetica', size=12)
    pdf.multi_cell(0, 7, TEXT.replace('Ingeniería', 'Ingenieria').replace('Formación', 'Formacion'))
    assert 'Ana Perez' in cv_import.extract_text(bytes(pdf.output()), 'CV.pdf')
    blank = FPDF(); blank.add_page()
    with pytest.raises(ValueError, match='texto legible'):
        cv_import.extract_text(bytes(blank.output()), 'scan.pdf')


def test_invalid_documents_are_rejected():
    for name, data in [('cv.doc', b'doc'), ('cv.docx', b'PKbad'), ('cv.pdf', b'%PDF-broken')]:
        with pytest.raises(ValueError):
            cv_import.extract_text(data, name)
    with pytest.raises(ValueError, match='8 MB'):
        cv_import.extract_text(b'x'*(cv_import.MAX_BYTES+1), 'cv.pdf')


def test_confirm_and_reimport_preserve_profile_facts(tmp_path):
    value = draft()
    cv_import.save_draft(value)
    assert cv_import.status()['draft']['name'] == 'Ana Perez'
    cv_import.apply(value)
    assert cv_import.status() == {'completed': True, 'draft': None}
    assert get_profile()['skills'] == {}
    cv_import.apply(value)
    profile = json.loads((tmp_path/'radar.db').with_name('cv_master.json').read_text())
    assert len(profile['experience']) == 1 and len(profile['education']) == 1
    assert profile['experience'][0]['company'] == 'ACME'


def test_import_file_failure_rolls_back_database(monkeypatch):
    monkeypatch.setattr(cv_import.cv_edit, '_backup_and_write', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):
        cv_import.apply(draft())
    assert get_profile() is None
    with connection() as conn:
        assert not conn.execute("SELECT 1 FROM app_settings WHERE key='setup_completed_v1'").fetchone()


def test_stdio_transport_works_with_actual_pipe_and_correlates_ids():
    code = "import sys,json\nfor line in sys.stdin:\n d=json.loads(line); print(json.dumps({'id':999,'result':{}}),flush=True); print(json.dumps({'id':d['id'],'result':{'ok':True}}),flush=True)"
    proc = subprocess.Popen([sys.executable, '-u', '-c', code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert ComputrabajoSource()._rpc(proc, 1, 'initialize', {}, timeout=2) == {'ok': True}
        assert ComputrabajoSource()._rpc(proc, 2, 'tools/call', {}, timeout=2) == {'ok': True}
    finally:
        proc.terminate(); proc.wait(timeout=5)


def test_stdio_timeout_is_bounded():
    proc = subprocess.Popen([sys.executable, '-u', '-c', 'import time; time.sleep(10)'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        with pytest.raises(TimeoutError):
            ComputrabajoSource()._rpc(proc, 1, 'initialize', {}, timeout=.05)
    finally:
        proc.terminate(); proc.wait(timeout=5)


def test_native_source_does_not_require_node(monkeypatch):
    from radar.sources import computrabajo_native

    monkeypatch.delenv('RADAR_COMPUTRABAJO_COMMAND', raising=False)
    monkeypatch.delenv('RADAR_COMPUTRABAJO_TRANSPORT', raising=False)
    monkeypatch.setattr(computrabajo_native, 'search', lambda *args: [])
    assert ComputrabajoSource().native
    assert ComputrabajoSource().search('analista', 'Lima') == []


def test_renderer_failure_opens_browser(monkeypatch):
    from radar import app

    monkeypatch.setitem(sys.modules, 'webview', Mock(create_window=Mock(side_effect=RuntimeError('no runtime'))))
    opened = Mock(); monkeypatch.setattr(app.webbrowser, 'open', opened)
    assert not app.open_window('http://127.0.0.1:8100/radar')
    opened.assert_called_once()


def test_place_catalog_covers_geometry_and_resolves_ambiguity():
    assert len(LIMA_PLACES) == 50 and len({p['id'] for p in LIMA_PLACES}) == 50
    assert infer_location('Bellavista, Callao').label == 'Bellavista'
    assert infer_location('Mi Perú, Callao').label == 'Mi Perú'
    assert infer_location('San Martín, Perú').precision == 'department'
    assert infer_location('Huachipa').place_id == infer_location('Lurigancho-Chosica').place_id


@pytest.mark.parametrize(('title','text','relevant'), [
    ('Ingeniero de diseño mecánico', 'Diseñar componentes mecánicos con SolidWorks.', True),
    ('Planner de mantenimiento', 'Funciones: Planificar mantenimiento mecanico de bombas y compresores.', True),
    ('Desarrollador de software', 'Requisitos: Ingeniería Mecánica y Python. Funciones: desarrollar software.', False),
    ('Técnico mecánico', 'Realizar mantenimiento mecanico de bombas.', False),
    ('Asistente administrativo', 'Requisitos: SolidWorks, AutoCAD e Ingeniería Mecánica.', False),
])
def test_mechanical_market_requires_occupational_evidence(title, text, relevant):
    from radar.careers import load_pack
    from radar.classify import classify
    from radar.domain.models import RawJob
    from radar.taxonomy import infer_relevance

    pack=load_pack('ingenieria_mecanica'); job=RawJob('test',title,'ACME','https://example.test',description=text)
    result=classify(job,pack)
    assert (infer_relevance(job,result.primary_area.value,pack).tier != 'out_of_focus') is relevant


def test_cv_mention_at_work_is_not_invented_education():
    result = cv_import.parse_text('Ana Perez\nExperiencia laboral\nTrabajé con estudiantes de Ingeniería Industrial en ACME.\nExcel avanzado', 'industrial_engineering')
    assert result['education'] == []


def test_update_notice_uses_semantic_version_and_fixed_destination(monkeypatch):
    from radar import updates

    monkeypatch.setattr(updates, '_cached', {})
    response = Mock(); response.json.return_value = {'tag_name':'v1.10.0', 'html_url':'https://untrusted.example/installer'}
    get = Mock(return_value=response); monkeypatch.setattr(updates.httpx, 'get', get)
    result = updates.check()
    assert result['available'] and result['url'] == updates.RELEASE_URL
    updates.check()
    assert get.call_count == 1
    assert updates.version('v1.10.0') > updates.version('v1.9.0')
    assert updates.version('1.1.0-beta') is None


def test_offline_update_check_does_not_break_startup(monkeypatch):
    from radar import updates

    monkeypatch.setattr(updates, '_cached', {})
    monkeypatch.setattr(updates.httpx, 'get', Mock(side_effect=updates.httpx.ConnectError('offline')))
    assert updates.check()['status'] == 'unavailable'


def test_preview_and_confirmation_api_are_separate():
    from fastapi.testclient import TestClient

    from radar.api import app

    client = TestClient(app)
    response = client.post('/api/me/cv/preview', data={'career_id':'industrial_engineering'}, files={'file':('CV.docx', word(TEXT))})
    assert response.status_code == 200 and get_profile() is None
    value = response.json()
    assert client.put('/api/me/setup/draft', json=value).status_code == 200
    assert client.post('/api/me/setup/confirm', json=value).status_code == 200
    assert client.get('/api/me/setup').json()['completed']


def test_geographic_scope_filters_before_limit():
    from datetime import UTC, datetime

    from radar.db.queries import list_jobs
    from radar.db.repository import ingest_jobs
    from radar.domain.models import RawJob

    for location in ('Arequipa', 'Bellavista, Callao', 'Perú', 'Lima'):
        ingest_jobs([RawJob('test','Analista de procesos','ACME','https://example.test/'+location,
                            location=location, description='Excel y mejora continua',published_at=datetime.now(UTC))])
    assert len(list_jobs(geo_scope='lima_callao')) == 2
    assert len(list_jobs(geo_scope='lima_callao', limit=1)) == 1
    assert len(list_jobs()) == 4


def test_reference_score_uses_selected_market_projection():
    from datetime import UTC, datetime

    from radar.db.queries import recommendations
    from radar.db.repository import ingest_jobs, recompute_scores, save_profile
    from radar.domain.models import RawJob
    from radar.settings import set_setting

    ingest_jobs([RawJob('test','Ingeniero de diseño mecánico','ACME','https://example.test/mec',
                       location='Lima',description='Diseñar componentes mecánicos en SolidWorks.',published_at=datetime.now(UTC))])
    set_setting('career', 'ingenieria_mecanica')
    profile_id=save_profile('Ana',None,['Diseño mecánico y simulación'],['Lima'],[],{})
    recompute_scores(profile_id)
    [job]=recommendations()['jobs']
    assert job['fit_assessment']['market_id'] == 'ingenieria_mecanica'
    assert job['fit_assessment']['dimensions']['area']['status'] == 'met'
    assert any(s['name']=='SolidWorks' for s in job['fit_assessment']['skills'])


def test_spanish_months_do_not_invent_missing_months():
    assert cv_import.dates_in('enero 2023 - diciembre 2024') == ['2023-01','2024-12']
    assert cv_import.dates_in('2023 - actualidad') == ['2023','actual']
    result=cv_import.parse_text('Ana Perez\nExperiencia laboral\nAnalista de procesos\nEmpresa: ACME SAC\nenero 2023 - diciembre 2024\n• Reportes de Excel\nHabilidades\nExcel', 'industrial_engineering')
    assert result['experience'][0]['company']=='ACME SAC'
    assert result['experience'][0]['to']=='2024-12'
