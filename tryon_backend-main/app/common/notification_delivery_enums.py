from enum import Enum


class NotificationChannelType(str, Enum):
    BACKOFFICE = "backoffice"
    EMAIL = "email"
    TELEGRAM = "telegram"
    SLACK = "slack"
    WEBHOOK = "webhook"


class NotificationDigestMode(str, Enum):
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"
    DISABLED = "disabled"


class NotificationChannelStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    INVALID = "invalid"


class NotificationMinimumPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"