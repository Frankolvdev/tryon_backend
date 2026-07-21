from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"
    DEAD_LETTER = "dead_letter"


class JobPriority(int, Enum):
    CRITICAL = 0
    HIGH = 25
    NORMAL = 50
    LOW = 75
    BACKGROUND = 100


class JobQueueName(str, Enum):
    DEFAULT = "default"
    AI = "ai"
    BILLING = "billing"
    SECURITY = "security"
    NOTIFICATIONS = "notifications"
    MAINTENANCE = "maintenance"
    WEBHOOKS = "webhooks"


class JobExecutionMode(str, Enum):
    INTERNAL = "internal"
    SIMULATED = "simulated"
    COMFYUI_LOCAL = "comfyui_local"
    RUNPOD_SERVERLESS = "runpod_serverless"
    EXTERNAL_API = "external_api"


class JobAttemptStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELED = "canceled"
    LOST = "lost"


class JobDependencyType(str, Enum):
    SUCCESS = "success"
    COMPLETION = "completion"