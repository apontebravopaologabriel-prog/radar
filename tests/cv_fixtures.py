"""Datos de prueba compartidos de los CVs."""

DESCRIPTION = (
    "Buscamos analista con Excel, Power BI y Python para reportes. Experiencia mínima de 1 año. "
    "Egresado o bachiller de Ingeniería Industrial. " * 6
)
PROFILE = {
    "name": "Ana Pérez & Co", "headline": "Ingeniería Industrial", "summary": "Estudiante orientada a datos.",
    "home_district": "La Victoria", "contact": {"email": "ana@example.com", "phone": "999 111 222"},
    "experience": [{
        "role": "Auxiliar", "company": "JAS", "location": "Lima", "from": "2023-01", "to": "2024-12",
        "bullets": ["Atendí llamadas de proveedores", "Ordené el almacén semanalmente", "Dashboard en Power BI de ventas",
                    "Controles de inventario en Excel", "Apoyé auditorías internas", "Redacté informes de turno"],
        "skills": [],
    }],
    "education": [{"institution": "UPC", "program": "Ingeniería Industrial", "from": "2021-03", "to": "2027-07",
                   "status": "en curso", "skills": []}],
    "certifications": [{"name": "Microsoft Office Specialist: Excel", "issuer": "UNI", "date": "2025-02"},
                       {"name": "Curso de liderazgo", "issuer": "UPC", "date": "2024-06"},
                       {"name": "Taller de oratoria", "issuer": "UPC", "date": "2023-06"},
                       {"name": "Seguridad industrial básica", "issuer": "SENATI", "date": "2022-06"}],
    "projects": [{"name": "Reporte automático", "description": "Consolidé reportes con Python", "skills": ["Python"], "date": "2026-03"},
                 {"name": "Feria de emprendimiento", "description": "Organicé un stand", "skills": []}],
    "languages": [{"name": "Español", "level": "nativo"}],
}
