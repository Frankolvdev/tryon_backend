from typing import Literal
from pydantic import BaseModel, Field

class DockerVolumeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]+$")
    driver: str = Field(default="local", min_length=1, max_length=100)
    labels: dict[str, str] = Field(default_factory=dict)

class DockerVolumeAction(BaseModel):
    force: bool = False

class DockerPathPayload(BaseModel):
    volume: str = Field(min_length=1, max_length=255)
    path: str = Field(default="", max_length=4000)

class DockerDirectoryCreate(DockerPathPayload):
    parents: bool = True

class DockerRenamePayload(DockerPathPayload):
    new_name: str = Field(min_length=1, max_length=255)

class DockerTransferPayload(BaseModel):
    source_volume: str = Field(min_length=1, max_length=255)
    source_path: str = Field(min_length=1, max_length=4000)
    destination_volume: str = Field(min_length=1, max_length=255)
    destination_path: str = Field(min_length=1, max_length=4000)
    overwrite: bool = False
    operation: Literal["copy", "move"] = "copy"

class DockerCommandPreview(BaseModel):
    operation: str = Field(min_length=1, max_length=100)
    parameters: dict[str, str | bool | None] = Field(default_factory=dict)

class RuntimeExportDestination(BaseModel):
    destination_type: Literal["local", "docker_volume"] = "local"
    docker_volume: str | None = Field(default=None, max_length=255)
    docker_path: str = Field(default="models", max_length=2000)
