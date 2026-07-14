from enum import Enum


class AccountVerificationMethod(str, Enum):
    OTP = "otp"
    EMAIL_LINK = "email_link"
    OTP_AND_EMAIL_LINK = "otp_and_email_link"
    DISABLED = "disabled"


class AccountVerificationPurpose(str, Enum):
    REGISTRATION = "registration"
    PASSWORD_RESET = "password_reset"
    EMAIL_CHANGE = "email_change"
    LOGIN_MFA = "login_mfa"


class AccountVerificationChallengeStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"