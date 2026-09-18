from __future__ import annotations

import argparse

from dotenv import load_dotenv

from radar.db.repository import (
    add_career_event,
    audit_data_quality,
    capture_market_snapshot,
    expire_stale_jobs,
    ingest_jobs,
    repair_data_quality,
    save_profile,
    track_application,
)
from radar.importers import load_job_file
from radar.liveness import check_application_status
from radar.pipeline import run_ingestion


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Busca, clasifica, deduplica y guarda ofertas")
    ingest.add_argument("--source", choices=["computrabajo", "jobspy"], default="computrabajo")
    ingest.add_argument("--query", required=True)
    ingest.add_argument("--location", default="Lima")
    ingest.add_argument("--limit", type=int, default=25)
    ingest.add_argument(
        "--max-age-days",
        type=int,
        default=14,
        help="Solo guarda ofertas fechadas dentro de este rango (por defecto: 14)",
    )
    profile = sub.add_parser("profile", help="Guarda el perfil explícitamente y recalcula scores")
    profile.add_argument("--name", required=True)
    profile.add_argument("--education", default=None)
    profile.add_argument("--area", action="append", default=[])
    profile.add_argument("--location", action="append", default=[])
    profile.add_argument(
        "--work-mode", action="append", choices=["onsite", "hybrid", "remote"], default=[]
    )
    event = sub.add_parser("career-event", help="Registra un hecho de evolución profesional")
    event.add_argument("--type", required=True, choices=["employment", "education", "course", "certification", "project", "interview", "achievement", "skill_update", "goal_update", "note"])
    event.add_argument("--title", required=True)
    event.add_argument("--description", default=None)
    event.add_argument("--started-on", default=None)
    event.add_argument("--ended-on", default=None)
    snapshot = sub.add_parser("market-snapshot", help="Guarda una fotografía del mercado")
    snapshot.add_argument("--date", default=None, dest="snapshot_date")
    application = sub.add_parser("application", help="Registra el estado de una postulación")
    application.add_argument("--job-id", required=True)
    application.add_argument("--status", default="saved", choices=["new", "reviewed", "saved", "ignored", "applied", "interview", "offer", "rejected", "expired"])
    application.add_argument("--notes", default=None)
    importer = sub.add_parser("import-jobs", help="Importa ofertas desde CSV/JSON de un portal")
    importer.add_argument("--file", required=True)
    importer.add_argument("--source", required=True, help="linkedin, bumeran, laborum, empleos-peru o ATS")
    sub.add_parser("repair-data", help="Repara modalidad, sector, salario y horario incompletos")
    sub.add_parser("audit-data", help="Audita duplicados, clasificación comercial y consistencia SQL")
    expire = sub.add_parser("expire-stale", help="Desactiva ofertas que ninguna fuente volvió a ver")
    expire.add_argument("--days", type=int, default=45, help="Días sin ser vista antes de desactivar (default: 45)")
    check = sub.add_parser("check-applications", help="Visita URLs activas y detecta ofertas cerradas")
    check.add_argument("--limit", type=int, default=50, help="Máximo de ofertas a revisar en esta corrida")
    check.add_argument("--recheck-after-days", type=int, default=3, help="Días antes de volver a revisar una oferta ya chequeada")
    profile.add_argument(
        "--skill",
        action="append",
        default=[],
        help="Skill=nivel; niveles: none,basic,intermediate,advanced",
    )
    args = parser.parse_args()
    if args.command == "ingest":
        print(
            run_ingestion(
                args.source, args.query, args.location, args.limit, args.max_age_days
            )
        )
    elif args.command == "profile":
        skills = dict(item.split("=", 1) for item in args.skill)
        invalid = {v for v in skills.values()} - {"none", "basic", "intermediate", "advanced"}
        if invalid:
            parser.error(f"niveles inválidos: {sorted(invalid)}")
        print(
            {
                "profile_id": save_profile(
                    args.name, args.education, args.area, args.location, args.work_mode, skills
                )
            }
        )
    elif args.command == "career-event":
        print({"event_id": add_career_event(None, args.type, args.title, args.description, args.started_on, args.ended_on)})
    elif args.command == "market-snapshot":
        print({"metrics_saved": capture_market_snapshot(args.snapshot_date)})
    elif args.command == "application":
        print({"application_id": track_application(args.job_id, args.status, args.notes)})
    elif args.command == "import-jobs":
        print(ingest_jobs(load_job_file(args.file, args.source)))
    elif args.command == "repair-data":
        print(repair_data_quality())
    elif args.command == "audit-data":
        print(audit_data_quality())
    elif args.command == "expire-stale":
        print({"deactivated": expire_stale_jobs(args.days)})
    elif args.command == "check-applications":
        print(check_application_status(args.limit, args.recheck_after_days))


if __name__ == "__main__":
    main()
