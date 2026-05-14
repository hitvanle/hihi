from __future__ import annotations

from pathlib import Path

from offline_app.data.db_paths import app_data_dir
from offline_app.data.medication_enrichment import apply_medication_enrichment
from offline_app.data.medication_repository import MedicationRepository


PROJECT_DB = Path(__file__).resolve().parents[1] / "hospital_medication.db"
APPDATA_DB = app_data_dir() / "hospital_medication.db"


def main() -> int:
    for db_path in [PROJECT_DB, APPDATA_DB]:
        repo = MedicationRepository(db_path=db_path)
        updated = apply_medication_enrichment(repo)
        total = len(repo.list_drugs())
        print(f"Seeded medication catalog into {db_path}; applied {updated} records; total {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
