from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.logging import get_logger
from app.evaluation.cost.cost_models import (
    CostBreakdown,
    CostCategory,
    CostEntry,
    CostSummary,
)
from app.models.cost import CostEntryModel, CostTrendModel

settings = get_settings()
logger = get_logger(__name__)


class CostTracker:
    def __init__(self, session: AsyncSession | None = None):
        """Create a cost tracker.

        When a session is supplied the cost entries join the caller's
        transaction, so a rolled-back run does not leave committed cost rows
        behind. Without a session the tracker opens its own short-lived
        session, which is only appropriate for standalone usage.
        """
        self.session = session
        self.pricing = {
            "openai": {
                "gpt-4": {"input": 0.03, "output": 0.06},
                "gpt-4-turbo": {"input": 0.01, "output": 0.03},
                "gpt-4o": {"input": 0.005, "output": 0.015},
                "gpt-4o-2024-08-06": {"input": 0.005, "output": 0.015},
                "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
                "text-embedding-3-small": {"input": 0.00002, "output": 0},
                "text-embedding-3-large": {"input": 0.00013, "output": 0},
            },
            "anthropic": {
                "claude-3-opus": {"input": 0.015, "output": 0.075},
                "claude-3-sonnet": {"input": 0.003, "output": 0.015},
                "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
                "claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
                "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
                "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
            },
            "google": {
                "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
                "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
            },
            "cohere": {
                "command-r-plus": {"input": 0.003, "output": 0.015},
                "command-r": {"input": 0.0005, "output": 0.0015},
            },
        }

    def calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        provider = (provider or "").lower()
        model_key = (model or "").lower()

        if provider in self.pricing and model_key:
            table = self.pricing[provider]
            pricing = table.get(model_key)
            if pricing is None:
                base_model = model_key.split("-202")[0].split("-20")[0]
                pricing = table.get(base_model)
            if pricing is None:
                # Only match when the configured model is a prefix of the
                # requested one. The reverse (a short requested name that
                # prefixes a longer configured name) priced an unknown model
                # as an unrelated one, and the dict iteration order made the
                # resulting price non-deterministic.
                candidates = [
                    (key, value)
                    for key, value in table.items()
                    if model_key.startswith(key)
                ]
                if candidates:
                    # Longest matching prefix wins.
                    pricing = max(candidates, key=lambda item: len(item[0]))[1]
            if pricing is not None:
                input_cost = (input_tokens / 1000) * pricing.get("input", 0)
                output_cost = (output_tokens / 1000) * pricing.get("output", 0)
                return input_cost + output_cost

        logger.warning("cost_unknown_model", provider=provider, model=model)
        return 0.0

    async def track_cost(
        self,
        category: CostCategory,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        run_id: UUID | str | None = None,
        test_case_id: UUID | str | None = None,
        metadata: dict[str, Any] = None,
    ) -> CostEntry:
        cost_usd = self.calculate_cost(provider, model, input_tokens, output_tokens)

        entry = CostEntry(
            id=uuid4(),
            run_id=run_id,
            test_case_id=test_case_id,
            category=category,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost_usd,
            metadata=metadata or {},
        )

        logger.info(
            "cost_tracked",
            category=category.value,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        async def _persist(session: AsyncSession) -> None:
            db_entry = CostEntryModel(
                id=entry.id,
                run_id=entry.run_id,
                test_case_id=entry.test_case_id,
                category=entry.category.value,
                provider=entry.provider,
                model=entry.model,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                total_tokens=entry.total_tokens,
                cost_usd=entry.cost_usd,
                currency=entry.currency,
                metadata_json=entry.metadata,
            )
            session.add(db_entry)

            trend = CostTrendModel(
                id=uuid4(),
                date=datetime.now(UTC),
                cost_usd=entry.cost_usd,
                token_count=entry.total_tokens,
                request_count=1,
                run_id=entry.run_id,
                provider=entry.provider,
                model=entry.model,
                category=entry.category.value,
            )
            session.add(trend)
            await session.flush()

        if self.session is not None:
            # Join the caller's transaction: the cost rows are committed
            # together with the run they describe.
            await _persist(self.session)
        else:
            async with get_async_session() as session:
                await _persist(session)

        return entry

    def check_limits(
        self,
        run_cost: float,
        daily_cost: float,
    ) -> dict[str, bool]:
        limits = {
            "run_limit_exceeded": run_cost > settings.COST_PER_RUN_LIMIT_USD,
            "daily_limit_exceeded": daily_cost > settings.COST_DAILY_LIMIT_USD,
        }
        return limits

    async def get_summary(
        self,
        start_time: datetime,
        end_time: datetime,
        run_ids: list[UUID] = None,
    ) -> CostSummary:
        from sqlalchemy import and_, func, select

        # The ``run_ids`` filter has to be applied to every breakdown query
        # as well as to the total. Previously only the total was filtered, so
        # the breakdowns contained every run in the period and did not sum to
        # the reported total.
        period = and_(
            CostEntryModel.created_at >= start_time,
            CostEntryModel.created_at <= end_time,
        )
        run_filter = CostEntryModel.run_id.in_([str(r) for r in run_ids]) if run_ids else None

        def _scope(stmt):
            if run_filter is not None:
                stmt = stmt.where(run_filter)
            return stmt

        async def _run() -> CostSummary:
            query = _scope(
                select(
                    func.sum(CostEntryModel.cost_usd).label("total_cost"),
                    func.sum(CostEntryModel.input_tokens).label("total_input"),
                    func.sum(CostEntryModel.output_tokens).label("total_output"),
                    func.sum(CostEntryModel.total_tokens).label("total_tokens"),
                ).where(period)
            )
            result = await session.execute(query)
            row = result.one()

            by_category_q = _scope(
                select(
                    CostEntryModel.category,
                    func.sum(CostEntryModel.cost_usd).label("cost"),
                )
                .where(period)
                .group_by(CostEntryModel.category)
            )

            by_provider_q = _scope(
                select(
                    CostEntryModel.provider,
                    func.sum(CostEntryModel.cost_usd).label("cost"),
                )
                .where(period)
                .group_by(CostEntryModel.provider)
            )

            by_model_q = _scope(
                select(
                    CostEntryModel.model,
                    func.sum(CostEntryModel.cost_usd).label("cost"),
                )
                .where(period)
                .group_by(CostEntryModel.model)
            )

            by_run_q = _scope(
                select(
                    CostEntryModel.run_id,
                    func.sum(CostEntryModel.cost_usd).label("cost"),
                )
                .where(period)
                .group_by(CostEntryModel.run_id)
            )

            by_category_res = await session.execute(by_category_q)
            by_provider_res = await session.execute(by_provider_q)
            by_model_res = await session.execute(by_model_q)
            by_run_res = await session.execute(by_run_q)

            by_category = {r.category: float(r.cost or 0) for r in by_category_res}
            by_provider = {r.provider: float(r.cost or 0) for r in by_provider_res}
            by_model = {r.model: float(r.cost or 0) for r in by_model_res}
            by_run = {str(r.run_id): float(r.cost or 0) for r in by_run_res if r.run_id}

            return CostSummary(
                total_cost_usd=float(row.total_cost or 0),
                total_input_tokens=int(row.total_input or 0),
                total_output_tokens=int(row.total_output or 0),
                total_tokens=int(row.total_tokens or 0),
                by_category=by_category,
                by_provider=by_provider,
                by_model=by_model,
                by_run=by_run,
                period_start=start_time,
                period_end=end_time,
            )

        if self.session is not None:
            return await _run()
        async with get_async_session() as session:
            return await _run()

    async def get_breakdown(self, run_id: UUID) -> CostBreakdown:
        from sqlalchemy import select

        async def _run() -> CostBreakdown:
            query = select(CostEntryModel).where(CostEntryModel.run_id == run_id)
            result = await session.execute(query)
            entries = list(result.scalars().all())

            total_cost = sum(e.cost_usd for e in entries)
            entries_data = [
                {
                    "id": str(e.id),
                    "category": e.category,
                    "provider": e.provider,
                    "model": e.model,
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "total_tokens": e.total_tokens,
                    "cost_usd": e.cost_usd,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entries
            ]

            # The reported window is the actual period covered by the
            # entries, not "now". The previous implementation returned
            # start_time == end_time == utcnow() and an empty run name.
            created = [e.created_at for e in entries if e.created_at is not None]
            start_time = min(created) if created else datetime.now(UTC)
            end_time = max(created) if created else datetime.now(UTC)

            run_name = ""
            from app.models.run import Run

            run_row = await session.execute(select(Run).where(Run.id == str(run_id)))
            run = run_row.scalar_one_or_none()
            if run is not None:
                run_name = f"Run {str(run.id)[:8]}"

            return CostBreakdown(
                run_id=run_id,
                run_name=run_name,
                total_cost_usd=total_cost,
                entries=entries_data,
                start_time=start_time,
                end_time=end_time,
            )

        if self.session is not None:
            return await _run()
        async with get_async_session() as session:
            return await _run()

    async def record_trend(
        self,
        run_id: UUID = None,
        provider: str = "",
        model: str = "",
        category: CostCategory = CostCategory.LLM_INFERENCE,
        cost_usd: float = 0.0,
        token_count: int = 0,
    ) -> None:
        async def _persist(session: AsyncSession) -> None:
            trend = CostTrendModel(
                id=uuid4(),
                date=datetime.now(UTC),
                cost_usd=cost_usd,
                # The argument was previously ignored and always written as 0,
                # so every token-based trend chart was empty.
                token_count=token_count,
                request_count=1,
                run_id=run_id,
                provider=provider,
                model=model,
                category=category.value,
            )
            session.add(trend)
            await session.flush()

        if self.session is not None:
            await _persist(self.session)
            return
        async with get_async_session() as session:
            await _persist(session)
