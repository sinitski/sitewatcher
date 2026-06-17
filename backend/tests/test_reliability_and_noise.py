from datetime import datetime, timedelta
from unittest.mock import MagicMock
import asyncio

import pytest


def _mk_check(is_up: bool, dt: datetime):
    c = MagicMock()
    c.is_up = is_up
    c.checked_at = dt
    return c


class TestIncidentsAndMttr:
    def test_no_checks(self):
        pytest.importorskip("sqlalchemy")
        from app.api.status import incidents_and_mttr_minutes
        incidents, mttr = incidents_and_mttr_minutes([])
        assert incidents == 0
        assert mttr == 0.0

    def test_single_incident_with_recovery(self):
        pytest.importorskip("sqlalchemy")
        from app.api.status import incidents_and_mttr_minutes

        base = datetime.utcnow()
        checks = [
            _mk_check(True, base),
            _mk_check(False, base + timedelta(minutes=1)),
            _mk_check(False, base + timedelta(minutes=2)),
            _mk_check(True, base + timedelta(minutes=6)),
        ]
        incidents, mttr = incidents_and_mttr_minutes(checks)
        assert incidents == 1
        assert mttr == 5.0


class TestRetryHeuristics:
    def test_should_retry_on_5xx(self):
        pytest.importorskip("apscheduler")
        from app.services.scheduler import _should_retry_check
        assert _should_retry_check({"is_up": False, "status_code": 503}) is True

    def test_should_retry_on_connection_failure(self):
        pytest.importorskip("apscheduler")
        from app.services.scheduler import _should_retry_check
        assert _should_retry_check({"is_up": False, "status_code": None}) is True

    def test_should_not_retry_when_up(self):
        pytest.importorskip("apscheduler")
        from app.services.scheduler import _should_retry_check
        assert _should_retry_check({"is_up": True, "status_code": 200}) is False


class TestRateLimit:
    def test_rate_limit_blocks_after_threshold(self):
        from app.services.rate_limit import rate_limit
        from fastapi import HTTPException

        dep = rate_limit("test", 1, 60)

        class Client:
            host = "127.0.0.1"

        class Req:
            client = Client()

        asyncio.run(dep(Req()))
        with pytest.raises(HTTPException):
            asyncio.run(dep(Req()))
