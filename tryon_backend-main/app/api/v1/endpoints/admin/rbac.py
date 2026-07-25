from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.rbac import (
    AssignPermissionToRoleRequest,
    AssignRoleToUserRequest,
    FeaturePermissionCreate,
    FeaturePermissionResponse,
    FeaturePermissionUpdate,
    PublicFeaturePermissionsResponse,
    RbacPermissionCreate,
    RbacPermissionResponse,
    RbacPermissionUpdate,
    RbacRoleCreate,
    RbacRoleResponse,
    RbacRoleUpdate,
    RbacRoleWithPermissionsResponse,
    UserRbacResponse,
)
from app.common.responses import SuccessResponse
from app.services.audit_service import audit_service
from app.services.rbac_service import rbac_service

router = APIRouter()


@router.get("/rbac/roles", response_model=list[RbacRoleResponse])
def list_roles(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rbac_service.list_roles(db)


@router.post("/rbac/roles", response_model=RbacRoleResponse)
def create_role(
    data: RbacRoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    role = rbac_service.create_role(db, data)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_role_created",
        entity_type="rbac_role",
        entity_id=str(role.id),
        description=f"Admin created RBAC role {role.key}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return role


@router.get("/rbac/roles/{role_id}", response_model=RbacRoleWithPermissionsResponse)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rbac_service.get_role_with_permissions(db, role_id)


@router.patch("/rbac/roles/{role_id}", response_model=RbacRoleResponse)
def update_role(
    role_id: int,
    data: RbacRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    role = rbac_service.update_role(db, role_id, data)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_role_updated",
        entity_type="rbac_role",
        entity_id=str(role.id),
        description=f"Admin updated RBAC role {role.key}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return role


@router.get("/rbac/permissions", response_model=list[RbacPermissionResponse])
def list_permissions(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rbac_service.list_permissions(db)


@router.post("/rbac/permissions", response_model=RbacPermissionResponse)
def create_permission(
    data: RbacPermissionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    permission = rbac_service.create_permission(db, data)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_permission_created",
        entity_type="rbac_permission",
        entity_id=str(permission.id),
        description=f"Admin created RBAC permission {permission.key}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return permission


@router.patch("/rbac/permissions/{permission_id}", response_model=RbacPermissionResponse)
def update_permission(
    permission_id: int,
    data: RbacPermissionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    permission = rbac_service.update_permission(db, permission_id, data)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_permission_updated",
        entity_type="rbac_permission",
        entity_id=str(permission.id),
        description=f"Admin updated RBAC permission {permission.key}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return permission


@router.post("/rbac/roles/{role_id}/permissions", response_model=SuccessResponse)
def assign_permission_to_role(
    role_id: int,
    data: AssignPermissionToRoleRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    rbac_service.assign_permission_to_role(
        db,
        role_id=role_id,
        permission_id=data.permission_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_permission_assigned",
        entity_type="rbac_role",
        entity_id=str(role_id),
        description=f"Admin assigned permission {data.permission_id} to role {role_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SuccessResponse(message="Permission assigned to role successfully.")


@router.delete(
    "/rbac/roles/{role_id}/permissions/{permission_id}",
    response_model=SuccessResponse,
)
def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    rbac_service.remove_permission_from_role(
        db,
        role_id=role_id,
        permission_id=permission_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_permission_removed",
        entity_type="rbac_role",
        entity_id=str(role_id),
        description=f"Admin removed permission {permission_id} from role {role_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SuccessResponse(message="Permission removed from role successfully.")


@router.get("/rbac/users/{user_id}", response_model=UserRbacResponse)
def get_user_rbac(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    from app.common.exceptions import NotFoundException
    from app.repositories.user_repository import user_repository

    user = user_repository.get_by_id(db, user_id)

    if not user:
        raise NotFoundException("User not found.")

    return rbac_service.get_user_rbac(db, user)


@router.post("/rbac/users/{user_id}/roles", response_model=SuccessResponse)
def assign_role_to_user(
    user_id: int,
    data: AssignRoleToUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    rbac_service.assign_role_to_user(
        db,
        user_id=user_id,
        role_id=data.role_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_role_assigned_to_user",
        entity_type="user",
        entity_id=str(user_id),
        description=f"Admin assigned role {data.role_id} to user {user_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SuccessResponse(message="Role assigned to user successfully.")


@router.delete("/rbac/users/{user_id}/roles/{role_id}", response_model=SuccessResponse)
def remove_role_from_user(
    user_id: int,
    role_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    rbac_service.remove_role_from_user(
        db,
        user_id=user_id,
        role_id=role_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_role_removed_from_user",
        entity_type="user",
        entity_id=str(user_id),
        description=f"Admin removed role {role_id} from user {user_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SuccessResponse(message="Role removed from user successfully.")


@router.get("/feature-permissions", response_model=list[FeaturePermissionResponse])
def list_feature_permissions(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rbac_service.list_feature_permissions(db)


@router.post("/feature-permissions", response_model=FeaturePermissionResponse)
def create_feature_permission(
    data: FeaturePermissionCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rbac_service.create_feature_permission(db, data)


@router.patch("/feature-permissions/{feature_id}", response_model=FeaturePermissionResponse)
def update_feature_permission(
    feature_id: int,
    data: FeaturePermissionUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rbac_service.update_feature_permission(db, feature_id, data)


@router.get("/feature-permissions/public", response_model=PublicFeaturePermissionsResponse)
def get_public_feature_permissions(
    db: Session = Depends(get_db),
):
    return PublicFeaturePermissionsResponse(
        features=rbac_service.list_public_feature_permissions(db),
    )