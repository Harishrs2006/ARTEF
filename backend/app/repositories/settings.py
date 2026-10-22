from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PromptVersionStatus
from app.models.feature_flag import FeatureFlag
from app.models.model_config import ModelConfig, PromptVersion
from app.repositories.base import BaseRepository


class ModelConfigRepository(BaseRepository[ModelConfig]):
    def __init__(self, session: AsyncSession):
        super().__init__(ModelConfig, session)

    async def get_by_role(self, role: str) -> ModelConfig | None:
        result = await self.session.execute(
            select(ModelConfig).where(ModelConfig.role == role, ModelConfig.is_active.is_(True))
        )
        return result.scalars().first()


class PromptVersionRepository(BaseRepository[PromptVersion]):
    def __init__(self, session: AsyncSession):
        super().__init__(PromptVersion, session)

    async def get_active_for_type(self, prompt_type: str) -> PromptVersion | None:
        result = await self.session.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_type == prompt_type,
                PromptVersion.status == PromptVersionStatus.ACTIVE,
            )
        )
        return result.scalars().first()

    async def get_by_type_version(self, prompt_type: str, version: str) -> PromptVersion | None:
        result = await self.session.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_type == prompt_type,
                PromptVersion.version == version,
            )
        )
        return result.scalars().first()

    async def demote_all(self, prompt_type: str) -> int:
        """Demote every ACTIVE prompt of a type so exactly one stays active."""
        result = await self.session.execute(
            update(PromptVersion)
            .where(
                PromptVersion.prompt_type == prompt_type,
                PromptVersion.status == PromptVersionStatus.ACTIVE,
            )
            .values(status=PromptVersionStatus.DEPRECATED)
        )
        return result.rowcount or 0


class FeatureFlagRepository(BaseRepository[FeatureFlag]):
    def __init__(self, session: AsyncSession):
        super().__init__(FeatureFlag, session)

    async def get_by_name(self, name: str) -> FeatureFlag | None:
        result = await self.session.execute(select(FeatureFlag).where(FeatureFlag.name == name))
        return result.scalars().first()
