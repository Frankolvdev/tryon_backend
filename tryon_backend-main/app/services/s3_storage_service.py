from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.services.integration_service import integration_service


class S3StorageService:
    def _get_config(self, db: Session):
        config = integration_service.get_config(db, IntegrationProvider.S3)

        if not config.is_enabled:
            raise ConflictException("S3 integration is disabled.")

        parsed_config = integration_service._parse_json(config.config_json)

        bucket = parsed_config.get("bucket")
        region = parsed_config.get("region")
        endpoint_url = parsed_config.get("endpoint_url") or None

        if not bucket:
            raise ConflictException("S3 bucket is not configured.")

        if not config.api_key:
            raise ConflictException("S3 access key is not configured.")

        if not config.api_secret:
            raise ConflictException("S3 secret key is not configured.")

        return config, parsed_config, bucket, region, endpoint_url

    def _client(self, db: Session):
        config, parsed_config, bucket, region, endpoint_url = self._get_config(db)

        return boto3.client(
            "s3",
            aws_access_key_id=config.api_key,
            aws_secret_access_key=config.api_secret,
            region_name=region or None,
            endpoint_url=endpoint_url,
        )

    def health_check(self, db: Session) -> dict[str, Any]:
        config, parsed_config, bucket, region, endpoint_url = self._get_config(db)
        client = self._client(db)

        try:
            client.head_bucket(Bucket=bucket)
            return {
                "healthy": True,
                "bucket": bucket,
                "region": region,
                "endpoint_url": endpoint_url,
            }
        except (BotoCoreError, ClientError) as error:
            raise ConflictException(f"S3 health check failed: {str(error)}")

    def upload_file(
        self,
        db: Session,
        *,
        local_path: str,
        object_key: str,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        config, parsed_config, bucket, region, endpoint_url = self._get_config(db)
        client = self._client(db)

        path = Path(local_path)

        if not path.exists():
            raise ConflictException("Local file does not exist.")

        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        client.upload_file(
            Filename=str(path),
            Bucket=bucket,
            Key=object_key,
            ExtraArgs=extra_args,
        )

        public_url = self.build_public_url(
            db=db,
            object_key=object_key,
        )

        return {
            "bucket": bucket,
            "object_key": object_key,
            "public_url": public_url,
            "size_bytes": path.stat().st_size,
        }

    def upload_bytes(
        self,
        db: Session,
        *,
        content: bytes,
        object_key: str,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        config, parsed_config, bucket, region, endpoint_url = self._get_config(db)
        client = self._client(db)

        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=content,
            **extra_args,
        )

        return {
            "bucket": bucket,
            "object_key": object_key,
            "public_url": self.build_public_url(db=db, object_key=object_key),
            "size_bytes": len(content),
        }

    def delete_file(
        self,
        db: Session,
        *,
        object_key: str,
    ) -> None:
        config, parsed_config, bucket, region, endpoint_url = self._get_config(db)
        client = self._client(db)

        client.delete_object(
            Bucket=bucket,
            Key=object_key,
        )

    def create_presigned_url(
        self,
        db: Session,
        *,
        object_key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        config, parsed_config, bucket, region, endpoint_url = self._get_config(db)
        client = self._client(db)

        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": object_key,
            },
            ExpiresIn=expires_in_seconds,
        )

    def build_public_url(
        self,
        db: Session,
        *,
        object_key: str,
    ) -> str:
        config, parsed_config, bucket, region, endpoint_url = self._get_config(db)

        cdn_base_url = parsed_config.get("cdn_base_url")

        if cdn_base_url:
            return f"{cdn_base_url.rstrip('/')}/{object_key}"

        if endpoint_url:
            return f"{endpoint_url.rstrip('/')}/{bucket}/{object_key}"

        if region:
            return f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"

        return f"https://{bucket}.s3.amazonaws.com/{object_key}"

    def generate_object_key(
        self,
        *,
        folder: str,
        original_filename: str,
    ) -> str:
        suffix = Path(original_filename).suffix
        return f"{folder}/{uuid4().hex}{suffix}".replace("\\", "/")


s3_storage_service = S3StorageService()