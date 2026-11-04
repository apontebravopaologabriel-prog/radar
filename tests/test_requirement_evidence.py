from datetime import UTC, datetime

import pytest

from radar.domain.models import RawJob
from radar.requirements import education_assessment, experience_assessment, month_set, skill_level
from radar.scoring import score_job


def education(program, status):
    return {"education": [{"program": program, "status": status}]}


@pytest.mark.parametrize(('program', 'status', 'expected'), [
    ('Ingeniería Industrial', 'Egresado', 'met'),
    ('Ingeniería Industrial', 'En curso', 'missing'),
    ('Administración Industrial', 'Titulado', 'missing'),
    ('Ingeniería de Sistemas', 'Bachiller', 'missing'),
])
def test_education_matches_program_and_grade(program, status, expected):
    result = education_assessment('Egresado o bachiller de Ingeniería Industrial.', education(program, status))
    assert result['status'] == expected
    assert result['quote']


def test_related_is_not_automatic_acceptance_and_preferred_does_not_override_required():
    profile = education('Ingeniería Industrial', 'Bachiller')
    assert education_assessment('Bachiller de Ingeniería de Sistemas o afines.', profile)['status'] == 'unknown'
    result = education_assessment('Bachiller de Ingeniería de Sistemas obligatorio. Bachiller de Ingeniería Industrial deseable.', profile)
    assert result['status'] == 'missing' and result['required']
    assert not education_assessment('Bachiller de Ingeniería de Sistemas deseable.', profile)['required']


def test_completed_degree_is_not_assumed_to_be_student_or_university():
    assert education_assessment('Bachiller de Ingeniería Industrial.', education('Ingeniería Industrial', 'Bachiller'))['status'] == 'met'
    assert education_assessment('Bachiller de Administración de empresas.', education('Administración de empresas', 'Titulado técnico'))['status'] == 'unknown'


def test_dates_overlap_future_and_invalid_months():
    entries = [{'from': '2024-01', 'to': '2024-12'}, {'from': '2024-07', 'to': '2025-12'},
               {'from': '2026-01', 'to': 'actualidad'}, {'from': '2024-13', 'to': ''}]
    assert len(month_set(entries, datetime(2025, 6, 1, tzinfo=UTC))) == 18


def test_experience_requires_dated_related_work():
    entries = [{'role': 'Cajero', 'from': '2020-01', 'to': '2024-12'}]
    description = 'Experiencia mínima de 3 años en análisis.'
    assert experience_assessment(description, {'experience': entries})['status'] == 'partial'
    entries[0]['role'] = 'Analista'
    assert experience_assessment(description, {'experience': entries})['status'] == 'met'
    assert experience_assessment(description, {})['status'] == 'unknown'
    assert experience_assessment('6 meses de experiencia.', {'experience': [{'from': '2024-01', 'to': '2024-06'}]})['status'] == 'met'
    assert experience_assessment('No se requiere 3 años de experiencia.', {'experience': entries})['status'] == 'unknown'


def test_skill_levels_do_not_spill_between_list_items():
    assert skill_level('SQL, Excel avanzado.', 'SQL')[0] is None
    assert skill_level('SQL, Excel avanzado.', 'Excel')[0] == 'advanced'
    assert skill_level('Nivel avanzado de SQL.', 'SQL')[0] == 'advanced'


def test_scores_expose_unknowns_and_declared_level_gap():
    job = RawJob('test', 'Analista', None, 'https://example.test', description='SQL avanzado.')
    basic = score_job(job, {'skills': {'SQL': 'basic'}}, {'SQL'}, None)
    advanced = score_job(job, {'skills': {'SQL': 'advanced'}}, {'SQL'}, None)
    unknown = score_job(job, {}, {'SQL'}, None)
    assert basic.total < advanced.total
    assert basic.assessment['declared_skill_gaps'] == ['SQL']
    assert basic.education == 0 and basic.assessment['dimensions']['education']['status'] == 'unknown'
    assert unknown.assessment['lower_bound'] == 0
    assert unknown.assessment['upper_bound'] == 100
    assert unknown.assessment['coverage'] == 0
    assert 'No es una probabilidad' in basic.reason


def test_saved_scores_become_stale_when_profile_or_offer_changes(tmp_path):
    import json

    from radar import insights
    from radar.db.database import connection
    from radar.db.queries import recommendations
    from radar.db.repository import ingest_jobs, recompute_scores, save_profile

    cv = tmp_path / 'cv_master.json'
    cv.write_text(json.dumps(education('Ingeniería Industrial', 'Bachiller')))
    ingest_jobs([RawJob('test', 'Analista de procesos', 'ACME', 'https://example.test/job',
                       description='Bachiller de Ingeniería Industrial. Mejorar procesos y usar SQL avanzado.',
                       published_at=datetime.now(UTC))])
    profile_id = save_profile('Test', '', ['Procesos'], ['Lima'], ['remote'], {'SQL': 'basic'})
    assert recompute_scores(profile_id) == 1
    with connection() as conn:
        job_id = conn.execute('SELECT id FROM jobs').fetchone()[0]
    fit = insights._fit(job_id, profile_id)
    assert not fit['stale'] and fit['assessment']['version'] == 'v2.1-evidence'
    assert recommendations()['jobs']
    cv.write_text(json.dumps(education('Ingeniería Industrial', 'En curso')))
    assert insights._fit(job_id, profile_id)['stale']
    assert not recommendations()['jobs']
    recompute_scores(profile_id)
    with connection() as conn:
        conn.execute("UPDATE jobs SET content_hash='changed' WHERE id=%s", (job_id,))
    assert insights._fit(job_id, profile_id)['stale']


def test_similar_positions_are_not_confirmed_by_unrelated_work():
    result = experience_assessment('Experiencia mínima de 1 año en puestos similares.',
                                   {'experience': [{'role': 'Cajero', 'from': '2020-01', 'to': '2024-12'}]})
    assert result['status'] == 'unknown'


def test_advanced_skill_is_not_established_by_a_certificate(tmp_path):
    from radar.cv_baseline import baseline
    from radar.db.database import connection
    from radar.db.repository import ingest_jobs

    ingest_jobs([RawJob('test', 'Analista', 'ACME', 'https://example.test/advanced', description='Excel avanzado.')])
    with connection() as conn:
        job_id = conn.execute('SELECT id FROM jobs').fetchone()[0]
    [item] = baseline(job_id, {'certifications': [{'name': 'Excel'}], 'tools_declared_in_db': {'Excel': 'basic'}})
    assert item['status'] == 'parcial'
    assert 'advanced' in item['reason']


def test_score_computation_does_not_lock_and_skips_changed_offer(monkeypatch):
    from radar.db import repository
    from radar.db.database import connection

    repository.ingest_jobs([RawJob('test', 'Analista de procesos', 'ACME', 'https://example.test/guard', description='Excel')])
    profile_id = repository.save_profile('Test', '', ['Procesos'], [], [], {})
    with connection() as conn:
        before = conn.execute('SELECT assessment FROM job_scores').fetchall()
    original = repository.score_job

    def concurrent_update(*args, **kwargs):
        with connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE jobs SET content_hash='newer-revision'")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, 'score_job', concurrent_update)
    assert repository.recompute_scores(profile_id) == 0
    with connection() as conn:
        assert conn.execute('SELECT assessment FROM job_scores').fetchall() == before


def test_employer_years_are_not_candidate_experience():
    result = experience_assessment('Empresa de servicios con 10 años de experiencia. Buscamos asistente.',
                                   {'experience': [{'from': '2024-01', 'to': '2024-12'}]})
    assert result['status'] == 'unknown' and not result['quote']
