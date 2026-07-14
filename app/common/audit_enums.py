from enum import Enum


class AuditActorType(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    API_KEY = "api_key"
    WEBHOOK = "webhook"
    PROVIDER = "provider"


class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    ENABLE = "enable"
    DISABLE = "disable"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PURCHASE = "purchase"
    REFUND = "refund"
    CHARGE = "charge"
    EXECUTE = "execute"
    RETRY = "retry"
    CANCEL = "cancel"
    APPROVE = "approve"
    REJECT = "reject"
    CONFIGURE = "configure"
    ROTATE_SECRET = "rotate_secret"
    ASSIGN_ROLE = "assign_role"
    REMOVE_ROLE = "remove_role"
    EXPORT = "export"
    IMPORT = "import"


class AuditResult(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"