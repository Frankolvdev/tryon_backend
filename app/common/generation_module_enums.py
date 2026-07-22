from enum import Enum


class GenerationExecutionEngine(str, Enum):
    SIMULATED = "simulated"
    LOCAL_DOCKER = "local_docker"
    RUNPOD_SERVERLESS = "runpod_serverless"


class GenerationModuleStepType(str, Enum):
    WORKFLOW = "workflow"
    PYTHON = "python"


class GenerationModuleInputType(str, Enum):
    IMAGE = "image"
    FILE = "file"
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"


class GenerationModuleOutputType(str, Enum):
    IMAGE = "image"
    IMAGES = "images"
    FILE = "file"
    JSON = "json"
    METADATA = "metadata"
