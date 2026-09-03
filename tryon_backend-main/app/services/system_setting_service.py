import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.enums import SettingCategory, SettingValueType
from app.common.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.models.system_setting import SystemSetting
from app.repositories.system_setting_repository import system_setting_repository
from app.schemas.system_setting import (
    PublicFrontendConfigResponse,
    PublicSystemSettingResponse,
    SystemSettingCreate,
    SystemSettingResponse,
    SystemSettingsByCategoryResponse,
    SystemSettingsGroupedResponse,
    SystemSettingUpdate,
)


class SystemSettingService:
    def _serialize_json(self, value: Any | None) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        return json.dumps(value)

    def _parse_json(self, value: str | None) -> Any | None:
        if value is None:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def _get_typed_value(self, setting: SystemSetting) -> Any | None:
        if setting.is_sensitive:
            return "********" if self._has_any_value(setting) else None

        if setting.value_type == SettingValueType.STRING.value:
            return setting.value_string

        if setting.value_type == SettingValueType.PASSWORD.value:
            return "********" if setting.value_string else None

        if setting.value_type == SettingValueType.INTEGER.value:
            return setting.value_integer

        if setting.value_type == SettingValueType.FLOAT.value:
            return setting.value_float

        if setting.value_type == SettingValueType.BOOLEAN.value:
            return setting.value_boolean

        if setting.value_type == SettingValueType.JSON.value:
            return self._parse_json(setting.value_json)

        return setting.value_string

    def _get_typed_default_value(self, setting: SystemSetting) -> Any | None:
        if setting.value_type == SettingValueType.STRING.value:
            return setting.default_value_string

        if setting.value_type == SettingValueType.PASSWORD.value:
            return "********" if setting.default_value_string else None

        if setting.value_type == SettingValueType.INTEGER.value:
            return setting.default_value_integer

        if setting.value_type == SettingValueType.FLOAT.value:
            return setting.default_value_float

        if setting.value_type == SettingValueType.BOOLEAN.value:
            return setting.default_value_boolean

        if setting.value_type == SettingValueType.JSON.value:
            return self._parse_json(setting.default_value_json)

        return setting.default_value_string

    def _has_any_value(self, setting: SystemSetting) -> bool:
        return any(
            [
                setting.value_string is not None,
                setting.value_integer is not None,
                setting.value_float is not None,
                setting.value_boolean is not None,
                setting.value_json is not None,
            ]
        )

    def _value_fields(
        self,
        value_type: str,
        value: Any | None,
        *,
        prefix: str = "value",
    ) -> dict:
        fields = {
            f"{prefix}_string": None,
            f"{prefix}_integer": None,
            f"{prefix}_float": None,
            f"{prefix}_boolean": None,
            f"{prefix}_json": None,
        }

        if value is None:
            return fields

        if value_type in [SettingValueType.STRING.value, SettingValueType.PASSWORD.value]:
            fields[f"{prefix}_string"] = str(value)

        elif value_type == SettingValueType.INTEGER.value:
            fields[f"{prefix}_integer"] = int(value)

        elif value_type == SettingValueType.FLOAT.value:
            fields[f"{prefix}_float"] = float(value)

        elif value_type == SettingValueType.BOOLEAN.value:
            if isinstance(value, bool):
                fields[f"{prefix}_boolean"] = value
            elif isinstance(value, str):
                fields[f"{prefix}_boolean"] = value.lower() in ["true", "1", "yes", "on"]
            else:
                fields[f"{prefix}_boolean"] = bool(value)

        elif value_type == SettingValueType.JSON.value:
            fields[f"{prefix}_json"] = self._serialize_json(value)

        else:
            fields[f"{prefix}_string"] = str(value)

        return fields

    def _to_response(self, setting: SystemSetting) -> SystemSettingResponse:
        return SystemSettingResponse(
            id=setting.id,
            category=setting.category,
            key=setting.key,
            label=setting.label,
            description=setting.description,
            value_type=setting.value_type,
            value=self._get_typed_value(setting),
            default_value=self._get_typed_default_value(setting),
            is_public=setting.is_public,
            is_editable=setting.is_editable,
            is_sensitive=setting.is_sensitive,
            requires_restart=setting.requires_restart,
            sort_order=setting.sort_order,
            created_at=setting.created_at,
            updated_at=setting.updated_at,
        )

    def list_settings(self, db: Session) -> list[SystemSettingResponse]:
        settings = system_setting_repository.list_all(db)
        return [self._to_response(setting) for setting in settings]

    def list_grouped_settings(self, db: Session) -> SystemSettingsGroupedResponse:
        settings = self.list_settings(db)

        grouped: dict[str, list[SystemSettingResponse]] = {}

        for setting in settings:
            category_key = setting.category.value
            grouped.setdefault(category_key, [])
            grouped[category_key].append(setting)

        return SystemSettingsGroupedResponse(categories=grouped)

    def list_settings_by_category(
        self,
        db: Session,
        category: SettingCategory,
    ) -> SystemSettingsByCategoryResponse:
        settings = system_setting_repository.list_by_category(db, category.value)

        return SystemSettingsByCategoryResponse(
            category=category,
            settings=[self._to_response(setting) for setting in settings],
        )

    def list_public_settings(self, db: Session) -> list[PublicSystemSettingResponse]:
        settings = system_setting_repository.list_public(db)

        return [
            PublicSystemSettingResponse(
                key=setting.key,
                value=self._get_typed_value(setting),
            )
            for setting in settings
        ]

    def get_public_frontend_config(self, db: Session) -> PublicFrontendConfigResponse:
        public_settings = {
            item.key: item.value
            for item in self.list_public_settings(db)
        }

        return PublicFrontendConfigResponse(
            app_name=public_settings.get("app_name"),
            support_email=public_settings.get("support_email"),
            frontend_base_url=public_settings.get("frontend_base_url"),
            registration_enabled=bool(public_settings.get("registration_enabled", True)),
            email_login_enabled=bool(public_settings.get("email_login_enabled", True)),
            social_login_enabled=bool(public_settings.get("social_login_enabled", False)),
            billing_enabled=bool(public_settings.get("billing_enabled", False)),
            subscriptions_enabled=bool(public_settings.get("subscriptions_enabled", False)),
            tryon_enabled=bool(public_settings.get("tryon_enabled", True)),
            footwear_tryon_enabled=bool(public_settings.get("footwear_tryon_enabled", True)),
            high_quality_enabled=bool(public_settings.get("high_quality_enabled", True)),
            maintenance_mode=bool(public_settings.get("maintenance_mode", False)),
            max_upload_size_mb=int(public_settings.get("max_upload_size_mb", 25)),
            public_settings=public_settings,
        )

    def create_setting(
        self,
        db: Session,
        data: SystemSettingCreate,
    ) -> SystemSettingResponse:
        existing = system_setting_repository.get_by_key(db, data.key)

        if existing:
            raise ConflictException("Setting key already exists.")

        value_fields = self._value_fields(data.value_type.value, data.value, prefix="value")
        default_value_fields = self._value_fields(
            data.value_type.value,
            data.default_value,
            prefix="default_value",
        )

        setting = system_setting_repository.create(
            db,
            data={
                "category": data.category.value,
                "key": data.key,
                "label": data.label,
                "description": data.description,
                "value_type": data.value_type.value,
                "is_public": data.is_public,
                "is_editable": data.is_editable,
                "is_sensitive": data.is_sensitive,
                "requires_restart": data.requires_restart,
                "sort_order": data.sort_order,
                **value_fields,
                **default_value_fields,
            },
        )

        return self._to_response(setting)

    def update_setting(
        self,
        db: Session,
        setting_id: int,
        data: SystemSettingUpdate,
    ) -> SystemSettingResponse:
        setting = system_setting_repository.get_by_id(db, setting_id)

        if not setting:
            raise NotFoundException("System setting not found.")

        if not setting.is_editable:
            raise ForbiddenException("This setting is not editable.")

        update_data = data.model_dump(exclude_unset=True)

        final_update_data = {}

        for field in [
            "label",
            "description",
            "is_public",
            "is_editable",
            "is_sensitive",
            "requires_restart",
            "sort_order",
        ]:
            if field in update_data:
                final_update_data[field] = update_data[field]

        if "value" in update_data:
            if (
                setting.value_type == SettingValueType.PASSWORD.value
                and update_data["value"] == "********"
            ):
                pass
            else:
                final_update_data.update(
                    self._value_fields(
                        setting.value_type,
                        update_data["value"],
                        prefix="value",
                    )
                )

        if "default_value" in update_data:
            final_update_data.update(
                self._value_fields(
                    setting.value_type,
                    update_data["default_value"],
                    prefix="default_value",
                )
            )

        updated_setting = system_setting_repository.update(
            db,
            db_obj=setting,
            data=final_update_data,
        )

        return self._to_response(updated_setting)

    def get_value(
        self,
        db: Session,
        key: str,
        default: Any | None = None,
    ) -> Any | None:
        setting = system_setting_repository.get_by_key(db, key)

        if not setting:
            return default

        value = self._get_typed_value(setting)

        if value is None:
            return self._get_typed_default_value(setting)

        return value


system_setting_service = SystemSettingService()