"""Async wrapper around the mygeotab SDK."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

import mygeotab


class GeotabClient:
    """Thread-safe async wrapper around mygeotab.API."""

    def __init__(self, username: str, password: str, database: str, server: str = "my.geotab.com"):
        self._username = username
        self._password = password
        self._database = database
        self._server = server
        self._api: mygeotab.API | None = None

    async def authenticate(self) -> None:
        """Authenticate and store the API handle."""
        api = mygeotab.API(
            username=self._username,
            password=self._password,
            database=self._database,
            server=self._server,
        )
        await asyncio.to_thread(api.authenticate)
        self._api = api

    def _require_api(self) -> mygeotab.API:
        if self._api is None:
            raise RuntimeError("Not authenticated — call authenticate() first")
        return self._api

    async def get(self, type_name: str, **kwargs: Any) -> list[dict]:
        """Generic get — wraps api.get()."""
        api = self._require_api()
        return await asyncio.to_thread(api.get, type_name, **kwargs)

    async def get_devices(self, active_only: bool = True) -> list[dict]:
        """Fetch devices. If active_only=True, uses fromDate=now to get only active devices."""
        if active_only:
            from datetime import datetime, timezone
            now_utc = datetime.now(timezone.utc).isoformat()
            return await self.get("Device", search={"fromDate": now_utc})
        return await self.get("Device")

    async def get_groups(self) -> list[dict]:
        return await self.get("Group")

    async def get_trips(
        self,
        from_date: date,
        to_date: date,
        device_search: dict | None = None,
        page_size: int = 25_000,
    ) -> list[dict]:
        """Fetch all trips in the date range using adaptive date-chunked pagination.

        MyGeotab's Trip endpoint has a server-side cap (observed ~25,000 per request).
        We start with month-sized chunks, then recursively bisect any chunk that hits
        the cap to ensure all trips are retrieved.

        Strategy:
          1. Generate month-sized date chunks.
          2. For each chunk, call Get with resultsLimit.
          3. If chunk returns >= page_size (hit the cap), bisect into two halves.
          4. Fetch all month chunks concurrently for speed.
        """
        api = self._require_api()
        all_trips: list[dict] = []
        lock = asyncio.Lock()

        async def fetch_chunk(chunk_start: date, chunk_end: date) -> None:
            search: dict[str, Any] = {
                "fromDate": datetime.combine(chunk_start, datetime.min.time()).isoformat(),
                "toDate": datetime.combine(chunk_end, datetime.max.time()).isoformat(),
            }
            if device_search:
                search["deviceSearch"] = device_search

            trips = await asyncio.to_thread(
                api.get,
                "Trip",
                search=search,
                resultsLimit=page_size,
            )

            if len(trips) >= page_size:
                # Hit the cap — bisect the date range
                if chunk_start == chunk_end:
                    # Single day still exceeded cap; can't bisect further — take what we have
                    async with lock:
                        all_trips.extend(trips)
                else:
                    mid = chunk_start + (chunk_end - chunk_start) // 2
                    await asyncio.gather(
                        fetch_chunk(chunk_start, mid),
                        fetch_chunk(mid + timedelta(days=1), chunk_end),
                    )
            else:
                async with lock:
                    all_trips.extend(trips)

        # Generate month-by-month date ranges
        current = date(from_date.year, from_date.month, 1)
        chunks: list[tuple[date, date]] = []
        while current <= to_date:
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)

            chunk_start = max(current, from_date)
            chunk_end = min(next_month - timedelta(days=1), to_date)
            chunks.append((chunk_start, chunk_end))
            current = next_month

        # Fetch all month chunks concurrently
        await asyncio.gather(*(fetch_chunk(s, e) for s, e in chunks))

        return all_trips

    async def get_exception_events_feed(
        self,
        rule_id: str,
        from_date: date,
        to_date: date,
        page_size: int = 50_000,
    ) -> list[dict]:
        """Fetch ExceptionEvents for a single rule using date-chunked Get with adaptive bisection.

        NOTE: This method was previously using GetFeed with cursor pagination, but that
        approach ignores the toDate filter when paging via fromVersion — leading to
        inflated counts (events from beyond the requested window leak in). We now use
        regular Get with date chunking, which respects the date filters.

        Strategy:
          1. Start with month-sized chunks (like get_trips).
          2. For each chunk, call Get with resultsLimit=50_000.
          3. If a chunk returns >= 50_000 rows (hit the cap), bisect into two halves
             and recursively fetch each half.
          4. Collect all events; deduplicate by id (shouldn't be duplicates with Get,
             but safe to handle edge cases).
        """
        api = self._require_api()
        by_id: dict[str, dict] = {}

        async def fetch_chunk(chunk_start: date, chunk_end: date) -> None:
            from_dt = datetime.combine(chunk_start, datetime.min.time()).isoformat()
            to_dt = datetime.combine(chunk_end, datetime.max.time()).isoformat()

            events = await asyncio.to_thread(
                api.get,
                "ExceptionEvent",
                search={
                    "fromDate": from_dt,
                    "toDate": to_dt,
                    "ruleSearch": {"id": rule_id},
                },
                resultsLimit=page_size,
            )

            if len(events) >= page_size:
                # Hit the cap — bisect the date range
                if chunk_start == chunk_end:
                    # Single day still exceeded 50k; can't bisect further — take what we have
                    for ev in events:
                        eid = ev.get("id")
                        if eid:
                            by_id[eid] = ev
                else:
                    mid = chunk_start + (chunk_end - chunk_start) // 2
                    await fetch_chunk(chunk_start, mid)
                    await fetch_chunk(mid + timedelta(days=1), chunk_end)
            else:
                for ev in events:
                    eid = ev.get("id")
                    if eid:
                        by_id[eid] = ev

        # Generate month-by-month date ranges (same pattern as get_trips)
        current = date(from_date.year, from_date.month, 1)
        chunks: list[tuple[date, date]] = []
        while current <= to_date:
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
            chunk_start = max(current, from_date)
            chunk_end = min(date(next_month.year, next_month.month, 1) - timedelta(days=1), to_date)
            chunks.append((chunk_start, chunk_end))
            current = next_month

        # Fetch all month chunks concurrently
        await asyncio.gather(*(fetch_chunk(s, e) for s, e in chunks))

        return list(by_id.values())

    async def get_status_data(self, diagnostic_ids: list[str], from_date: date, to_date: date) -> list[dict]:
        """Fetch StatusData for a list of diagnostic IDs."""
        from_dt = datetime.combine(from_date, datetime.min.time()).isoformat()
        to_dt = datetime.combine(to_date, datetime.max.time()).isoformat()

        all_data: list[dict] = []
        for diag_id in diagnostic_ids:
            data = await self.get(
                "StatusData",
                search={
                    "fromDate": from_dt,
                    "toDate": to_dt,
                    "diagnosticSearch": {"id": diag_id},
                },
            )
            all_data.extend(data)
        return all_data

    async def get_battery_fault_data(self, from_date: date, to_date: date) -> list[dict]:
        """Fetch FaultData for battery health (Geotab/System sources, codes 131/290/135).

        Chunks by month to avoid the 50,000 results limit.
        """
        api = self._require_api()
        now_utc = datetime.now().isoformat()
        all_data: list[dict] = []

        current = date(from_date.year, from_date.month, 1)
        while current <= to_date:
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
            chunk_start = max(current, from_date)
            chunk_end = min(date(next_month.year, next_month.month, 1).fromordinal(next_month.toordinal() - 1), to_date)

            chunk = await asyncio.to_thread(
                api.get,
                "FaultData",
                resultsLimit=50_000,
                search={
                    "fromDate": datetime.combine(chunk_start, datetime.min.time()).isoformat(),
                    "toDate": datetime.combine(chunk_end, datetime.max.time()).isoformat(),
                    "excludeDismissed": True,
                    "diagnosticSearch": {
                        "sourceSearch": {
                            "ids": ["SourceGeotabGoId", "SourceSystemId"],
                        },
                    },
                    "deviceSearch": {
                        "fromDate": now_utc,
                    },
                },
            )
            all_data.extend(chunk)
            current = next_month

        return all_data

    async def get_engine_fault_data(self, from_date: date, to_date: date) -> list[dict]:
        """Fetch FaultData for engine/DTC codes (OBD and proprietary sources).

        Chunks by month to avoid the 50,000 results limit.
        """
        api = self._require_api()
        now_utc = datetime.now().isoformat()
        all_data: list[dict] = []

        current = date(from_date.year, from_date.month, 1)
        while current <= to_date:
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
            chunk_start = max(current, from_date)
            chunk_end = min(date(next_month.year, next_month.month, 1).fromordinal(next_month.toordinal() - 1), to_date)

            chunk = await asyncio.to_thread(
                api.get,
                "FaultData",
                resultsLimit=50_000,
                search={
                    "fromDate": datetime.combine(chunk_start, datetime.min.time()).isoformat(),
                    "toDate": datetime.combine(chunk_end, datetime.max.time()).isoformat(),
                    "excludeDismissed": True,
                    "diagnosticSearch": {
                        "sourceSearch": {
                            "ids": [
                                "SourceAIModelId",
                                "SourceBrpId",
                                "SourceGmcccId",
                                "SourceJ1708Id",
                                "SourceJ1939Id",
                                "SourceLegacyId",
                                "SourceObdId",
                                "SourceObdSaId",
                                "SourceProprietaryId",
                                "SourceThirdPartyId",
                            ],
                        },
                    },
                    "deviceSearch": {
                        "fromDate": now_utc,
                    },
                },
            )
            all_data.extend(chunk)
            current = next_month

        return all_data

    async def get_rule(self, rule_id: str) -> dict | None:
        try:
            results = await self.get("Rule", search={"id": rule_id})
            return results[0] if results else None
        except Exception:
            return None

    async def get_all_rules(self) -> list[dict]:
        """Get all rules in the database."""
        return await self.get("Rule")

    async def get_user(self, username: str) -> dict | None:
        """Get user info including displayCurrency."""
        try:
            results = await self.get("User", search={"name": username})
            return results[0] if results else None
        except Exception:
            return None

    async def resolve_diagnostic(self, diagnostic_id: str) -> dict | None:
        results = await self.get("Diagnostic", search={"id": diagnostic_id})
        return results[0] if results else None

    async def resolve_diagnostics_bulk(self, diagnostic_ids: list[str]) -> dict[str, dict]:
        """Batch-resolve diagnostic IDs to their full objects (including code, name).

        Returns dict: {diagnostic_id: {id, code, name, ...}}
        """
        if not diagnostic_ids:
            return {}

        # Deduplicate
        unique_ids = list(set(diagnostic_ids))

        # Fetch all diagnostics (Geotab doesn't support multi-ID search, so get all)
        # But for efficiency, we can filter by IDs if small set, or fetch all and filter
        # For large fleets, fetching all diagnostics once is more efficient than N calls
        all_diags = await self.get("Diagnostic")

        result: dict[str, dict] = {}
        for d in all_diags:
            did = d.get("id")
            if did in unique_ids:
                result[did] = d

        return result

    @classmethod
    def from_credentials(cls, creds: dict) -> "GeotabClient":
        return cls(
            username=creds["username"],
            password=creds["password"],
            database=creds["database"],
            server=creds.get("server", "my.geotab.com"),
        )
