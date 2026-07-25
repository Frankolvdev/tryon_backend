import fnmatch
import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.rate_limit_enums import RateLimitScope
from app.models.rate_limit_policy import RateLimitPolicy
from app.repositories.rate_limit_policy_repository import (
    rate_limit_policy_repository,
)
from app.schemas.rate_limit import (
    RateLimitPolicyCreate,
    RateLimitPolicyListResponse,
    RateLimitPolicyResponse,
    RateLimitPolicyUpdate,
)


class RateLimitPolicyService:
    def _serialize_json(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_json(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _to_response(
        self,
        policy: RateLimitPolicy,
    ) -> RateLimitPolicyResponse:
        return RateLimitPolicyResponse(
            id=policy.id,
            key=policy.key,
            name=policy.name,
            description=policy.description,
            route_pattern=policy.route_pattern,
            http_method=policy.http_method,
            scope=policy.scope,
            algorithm=policy.algorithm,
            request_limit=policy.request_limit,
            window_seconds=policy.window_seconds,
            burst_limit=policy.burst_limit,
            block_seconds=policy.block_seconds,
            priority=policy.priority,
            applies_to_authenticated=(
                policy.applies_to_authenticated
            ),
            applies_to_anonymous=(
                policy.applies_to_anonymous
            ),
            include_headers=policy.include_headers,
            is_enabled=policy.is_enabled,
            metadata=self._parse_json(
                policy.metadata_json
            ),
            created_at=policy.created_at,
            updated_at=policy.updated_at,
        )

    def get_policy(
        self,
        db: Session,
        *,
        policy_id: int,
    ) -> RateLimitPolicy:
        policy = rate_limit_policy_repository.get_by_id(
            db,
            policy_id,
        )

        if not policy:
            raise NotFoundException(
                "Rate limit policy not found."
            )

        return policy

    def get_by_key(
        self,
        db: Session,
        *,
        key: str,
    ) -> RateLimitPolicy:
        policy = rate_limit_policy_repository.get_by_key(
            db,
            key,
        )

        if not policy:
            raise NotFoundException(
                "Rate limit policy not found."
            )

        return policy

    def list_policies(
        self,
        db: Session,
        *,
        search: str | None = None,
        is_enabled: bool | None = None,
        scope: RateLimitScope | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> RateLimitPolicyListResponse:
        scope_value = scope.value if scope else None

        policies = rate_limit_policy_repository.list_filtered(
            db,
            search=search,
            is_enabled=is_enabled,
            scope=scope_value,
            skip=skip,
            limit=limit,
        )

        total = rate_limit_policy_repository.count_filtered(
            db,
            search=search,
            is_enabled=is_enabled,
            scope=scope_value,
        )

        return RateLimitPolicyListResponse(
            items=[
                self._to_response(policy)
                for policy in policies
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def create_policy(
        self,
        db: Session,
        *,
        data: RateLimitPolicyCreate,
    ) -> RateLimitPolicyResponse:
        existing = rate_limit_policy_repository.get_by_key(
            db,
            data.key,
        )

        if existing:
            raise ConflictException(
                "Rate limit policy key already exists."
            )

        policy = rate_limit_policy_repository.create(
            db,
            data={
                "key": data.key,
                "name": data.name,
                "description": data.description,
                "route_pattern": data.route_pattern,
                "http_method": data.http_method,
                "scope": data.scope.value,
                "algorithm": data.algorithm.value,
                "request_limit": data.request_limit,
                "window_seconds": data.window_seconds,
                "burst_limit": data.burst_limit,
                "block_seconds": data.block_seconds,
                "priority": data.priority,
                "applies_to_authenticated": (
                    data.applies_to_authenticated
                ),
                "applies_to_anonymous": (
                    data.applies_to_anonymous
                ),
                "include_headers": data.include_headers,
                "is_enabled": data.is_enabled,
                "metadata_json": self._serialize_json(
                    data.metadata
                ),
            },
        )

        return self._to_response(policy)

    def update_policy(
        self,
        db: Session,
        *,
        policy_id: int,
        data: RateLimitPolicyUpdate,
    ) -> RateLimitPolicyResponse:
        policy = self.get_policy(
            db,
            policy_id=policy_id,
        )

        values = data.model_dump(
            exclude_unset=True,
        )

        final_data: dict[str, Any] = {}

        direct_fields = [
            "name",
            "description",
            "route_pattern",
            "http_method",
            "request_limit",
            "window_seconds",
            "burst_limit",
            "block_seconds",
            "priority",
            "applies_to_authenticated",
            "applies_to_anonymous",
            "include_headers",
            "is_enabled",
        ]

        for field in direct_fields:
            if field in values:
                final_data[field] = values[field]

        if (
            "scope" in values
            and values["scope"] is not None
        ):
            final_data["scope"] = values["scope"].value

        if (
            "algorithm" in values
            and values["algorithm"] is not None
        ):
            final_data["algorithm"] = (
                values["algorithm"].value
            )

        if "metadata" in values:
            final_data["metadata_json"] = (
                self._serialize_json(
                    values["metadata"]
                )
            )

        updated = rate_limit_policy_repository.update(
            db,
            db_obj=policy,
            data=final_data,
        )

        return self._to_response(updated)

    def set_enabled(
        self,
        db: Session,
        *,
        policy_id: int,
        enabled: bool,
    ) -> RateLimitPolicyResponse:
        policy = self.get_policy(
            db,
            policy_id=policy_id,
        )

        policy.is_enabled = enabled

        db.add(policy)
        db.commit()
        db.refresh(policy)

        return self._to_response(policy)

    def delete_policy(
        self,
        db: Session,
        *,
        policy_id: int,
    ) -> None:
        policy = self.get_policy(
            db,
            policy_id=policy_id,
        )

        rate_limit_policy_repository.delete(
            db,
            db_obj=policy,
        )

    def match_policy(
        self,
        db: Session,
        *,
        route: str,
        http_method: str,
        is_authenticated: bool,
    ) -> RateLimitPolicy | None:
        policies = (
            rate_limit_policy_repository.list_enabled(db)
        )

        normalized_method = http_method.upper()

        for policy in policies:
            if (
                policy.http_method
                and policy.http_method.upper()
                != normalized_method
            ):
                continue

            if (
                is_authenticated
                and not policy.applies_to_authenticated
            ):
                continue

            if (
                not is_authenticated
                and not policy.applies_to_anonymous
            ):
                continue

            if fnmatch.fnmatch(
                route,
                policy.route_pattern,
            ):
                return policy

        return None


rate_limit_policy_service = RateLimitPolicyService()