from pathlib import Path

import pytest
from alembic import command, script
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


@pytest.fixture()
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, str]:
    db_path = tmp_path / "alembic.db"
    database_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("prepend_sys_path", str(backend_root))
    return config, database_url


def test_alembic_revision_graph_has_single_expected_head(alembic_config: tuple[Config, str]) -> None:
    config, _ = alembic_config
    directory = script.ScriptDirectory.from_config(config)

    assert directory.get_heads() == ["d7f0a1b2c3e4"]
    assert directory.get_revision("d7f0a1b2c3e4").down_revision == "c4e8f1a2b3d9"
    assert directory.get_revision("c4e8f1a2b3d9").down_revision == "a7d9e1f3c5b7"
    assert directory.get_revision("a7d9e1f3c5b7").down_revision == "f1a2b3c4d5e6"
    assert directory.get_revision("f1a2b3c4d5e6").down_revision == "e3c1d2f4a5b6"
    assert directory.get_revision("e3c1d2f4a5b6").down_revision == "b2f6d8a9c1e3"
    assert directory.get_revision("b2f6d8a9c1e3").down_revision == "c74e9b1a6d02"
    assert directory.get_revision("c74e9b1a6d02").down_revision == "a1f4d7e9c2b6"
    assert directory.get_revision("a1f4d7e9c2b6").down_revision == "f6b2c9d4e7a1"
    assert directory.get_revision("f6b2c9d4e7a1").down_revision == "d4a8c1f0b2e3"

    chain = [revision.revision for revision in directory.walk_revisions()]
    assert chain == [
        "d7f0a1b2c3e4",
        "c4e8f1a2b3d9",
        "a7d9e1f3c5b7",
        "f1a2b3c4d5e6",
        "e3c1d2f4a5b6",
        "b2f6d8a9c1e3",
        "c74e9b1a6d02",
        "a1f4d7e9c2b6",
        "f6b2c9d4e7a1",
        "d4a8c1f0b2e3",
        "c9f2a7b41e60",
        "b7c4e1d9a3f2",
        "0c33b0405545",
    ]


def test_alembic_upgrade_to_head_has_no_drift(alembic_config: tuple[Config, str]) -> None:
    config, _ = alembic_config

    command.upgrade(config, "head")
    command.check(config)


def test_schema_parity_for_p0_objects(alembic_config: tuple[Config, str]) -> None:
    config, database_url = alembic_config
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)

        tables = set(inspector.get_table_names())
        assert {
            "users",
            "etl_jobs",
            "etl_mapping_decisions",
            "synthmed_source_datasets",
            "synthmed_generated_datasets",
            "synthmed_generation_jobs",
            "synthmed_generation_configs",
            "synthmed_evaluation_reports",
            "synthmed_comparisons",
            "synthmed_utility_evaluations",
            "synthmed_dataset_versions",
            "synthmed_dataset_lineage",
            "synthmed_generation_config_snapshots",
            "synthmed_experiments",
            "research_reports",
        }.issubset(tables)

        dataset_columns = {item["name"] for item in inspector.get_columns("datasets")}
        assert {
            "origin",
            "source_generated_dataset_id",
            "source_repository_dataset_id",
            "generation_job_id",
            "generation_model",
            "provenance_json",
        }.issubset(dataset_columns)
        dataset_indexes = {item["name"] for item in inspector.get_indexes("datasets")}
        assert "uq_datasets_source_generated_dataset_id" in dataset_indexes

        job_indexes = {item["name"] for item in inspector.get_indexes("synthmed_generation_jobs")}
        assert "ix_synthmed_generation_jobs_status" in job_indexes

        config_uniques = inspector.get_unique_constraints("synthmed_generation_configs")
        assert any(item.get("name") == "uq_synthmed_config_job" for item in config_uniques)

        mapping_indexes = inspector.get_indexes("etl_mapping_decisions")
        assert any(
            item.get("name") == "uq_etl_mapping_decisions_job_source" and item.get("unique") == 1
            for item in mapping_indexes
        )

        user_columns = {item["name"]: item for item in inspector.get_columns("users")}
        assert user_columns["email"]["type"].length == 320

        source_columns = {item["name"]: item for item in inspector.get_columns("synthmed_source_datasets")}
        assert source_columns["upload_status"].get("default") is not None
        assert source_columns["row_count"].get("default") is not None

        utility_columns = {item["name"] for item in inspector.get_columns("synthmed_utility_evaluations")}
        assert {"report_sha256", "report_csv_sha256", "report_pdf_sha256"}.issubset(utility_columns)

        comparison_indexes = {item["name"] for item in inspector.get_indexes("synthmed_comparisons")}
        assert "ix_synthmed_comparison_owner_created" in comparison_indexes
        assert "ix_synthmed_comparison_generated_created" in comparison_indexes
    finally:
        engine.dispose()


def test_upgrade_downgrade_round_trip_preserves_existing_data(
    alembic_config: tuple[Config, str],
) -> None:
    config, database_url = alembic_config
    command.upgrade(config, "f6b2c9d4e7a1")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, full_name, hashed_password, role, "
                    "organisation, title, is_active) VALUES "
                    "('migration-user', 'migration@example.test', 'Migration User', 'hash', "
                    "'Contributor', 'Test Org', 'Researcher', 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO etl_mapping_decisions (id, job_id, source, proposed_target, "
                    "target, decision, confidence, note, decided_by_id, decided_at) VALUES "
                    "('migration-decision', 'migration-job', 'age', 'age_years', 'age_years', "
                    "'Approved', 1.0, 'Preserved row', 'migration-user', CURRENT_TIMESTAMP)"
                )
            )

        command.upgrade(config, "head")
        command.downgrade(config, "f6b2c9d4e7a1")
        command.upgrade(config, "head")

        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT email FROM users WHERE id = 'migration-user'")
            ) == "migration@example.test"
            assert connection.scalar(
                text("SELECT note FROM etl_mapping_decisions WHERE id = 'migration-decision'")
            ) == "Preserved row"

        command.check(config)
    finally:
        engine.dispose()
