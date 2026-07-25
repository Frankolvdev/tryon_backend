from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


VALID_GALLERY_VISIBILITIES = {
    "private",
    "registered_users",
    "public",
}


class UserGalleryItemCreate(BaseModel):
    tryon_job_id: int | None = Field(
        default=None,
        ge=1,
    )

    source_file_id: int | None = Field(
        default=None,
        ge=1,
    )

    result_file_id: int = Field(
        ge=1,
    )

    title: str | None = Field(
        default=None,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    category: str = Field(
        default="tryon",
        min_length=1,
        max_length=50,
    )

    visibility: str = Field(
        default="private",
        max_length=30,
    )

    @field_validator(
        "category",
        mode="before",
    )
    @classmethod
    def normalize_category(
        cls,
        value: str,
    ) -> str:
        return str(value).strip().lower()

    @field_validator(
        "visibility",
        mode="before",
    )
    @classmethod
    def validate_visibility(
        cls,
        value: str,
    ) -> str:
        normalized = str(value).strip().lower()

        if normalized not in VALID_GALLERY_VISIBILITIES:
            raise ValueError(
                "Invalid gallery visibility."
            )

        return normalized


class UserGalleryItemUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    visibility: str | None = Field(
        default=None,
        max_length=30,
    )

    is_favorite: bool | None = None
    is_archived: bool | None = None

    @field_validator(
        "visibility",
        mode="before",
    )
    @classmethod
    def validate_visibility(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().lower()

        if normalized not in VALID_GALLERY_VISIBILITIES:
            raise ValueError(
                "Invalid gallery visibility."
            )

        return normalized


class UserGalleryItemResponse(BaseModel):
    id: int
    user_id: int

    tryon_job_id: int | None

    source_file_id: int | None
    result_file_id: int

    title: str | None
    description: str | None

    category: str
    visibility: str

    is_favorite: bool
    is_archived: bool
    is_deleted: bool

    source_url: str | None
    result_url: str

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserGalleryListResponse(BaseModel):
    items: list[UserGalleryItemResponse]

    total: int
    skip: int
    limit: int


class UserGalleryDownloadResponse(BaseModel):
    gallery_item_id: int

    file_id: int
    download_url: str

    expires_in_seconds: int


class UserGalleryComparisonResponse(BaseModel):
    gallery_item_id: int

    source_url: str | None
    result_url: str


class UserGalleryOperationResponse(BaseModel):
    success: bool
    message: str