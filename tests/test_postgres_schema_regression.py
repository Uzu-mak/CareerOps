from sqlalchemy import Text
from careerops.db.models import SourceConfig
from careerops.db.init import starter_source_specs
from pathlib import Path


def test_source_status_is_unbounded_text_for_long_status_and_error_messages():
    assert isinstance(SourceConfig.__table__.c.last_status.type, Text)
    # This exact class of starter status caused PostgreSQL VARCHAR(40) startup failure.
    statuses=[spec[5] for spec in starter_source_specs() if spec[5]]
    assert any(len(s) > 40 for s in statuses)


def test_startup_contains_postgres_compatibility_widening():
    src=(Path(__file__).resolve().parents[1]/'careerops/db/init.py').read_text()
    assert 'ALTER TABLE source_configs ALTER COLUMN last_status TYPE TEXT' in src
    assert 'ALTER TABLE source_configs ALTER COLUMN token_or_url TYPE TEXT' in src
