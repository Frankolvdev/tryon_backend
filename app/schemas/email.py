from pydantic import BaseModel, EmailStr, Field


class EmailSendTestRequest(BaseModel):
    to_email: EmailStr
    subject: str = Field(default="SMTP test email")
    body: str = Field(default="This is a test email from AI Try-On Platform.")


class EmailSendResponse(BaseModel):
    sent: bool
    message: str