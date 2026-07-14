from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import FeaturePermissionKey, RbacAction, RbacModule


class RbacPermissionCreate(BaseModel):
    key: str = Field(min_length=3, max_length=255)
    module: RbacModule
    action: RbacAction
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    is_system: bool = True
    is_active: bool = True


class RbacPermissionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class RbacPermissionResponse(BaseModel):
    id: int
    key: str
    module: RbacModule
    action: RbacAction
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RbacRoleCreate(BaseModel):
    key: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    is_system: bool = False
    is_active: bool = True


class RbacRoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class RbacRoleResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RbacRoleWithPermissionsResponse(RbacRoleResponse):
    permissions: list[RbacPermissionResponse] = []


class AssignPermissionToRoleRequest(BaseModel):
    permission_id: int


class AssignRoleToUserRequest(BaseModel):
    role_id: int


class UserRbacResponse(BaseModel):
    user_id: int
    role_keys: list[str]
    permission_keys: list[str]


class FeaturePermissionCreate(BaseModel):
    key: FeaturePermissionKey | str
    name: str
    description: str | None = None
    is_enabled: bool = True
    is_public: bool = False


class FeaturePermissionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
    is_public: bool | None = None


class FeaturePermissionResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    is_enabled: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicFeaturePermissionsResponse(BaseModel):
    features: dict[str, bool]