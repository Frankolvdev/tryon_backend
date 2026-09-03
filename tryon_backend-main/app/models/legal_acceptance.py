from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.common.time import utc_now
from app.db.database import Base

class LegalAcceptance(Base):
    __tablename__ = "legal_acceptances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    legal_document_id: Mapped[int] = mapped_column(ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    document_version: Mapped[str] = mapped_column(String(40), nullable=False)
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    context_reference: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_purchase_id: Mapped[int | None] = mapped_column(ForeignKey("token_purchases.id", ondelete="SET NULL"), nullable=True, index=True)
    billing_payment_id: Mapped[int | None] = mapped_column(ForeignKey("billing_payments.id", ondelete="SET NULL"), nullable=True, index=True)
    token_bag_id: Mapped[int | None] = mapped_column(ForeignKey("token_value_lots.id", ondelete="SET NULL"), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    __table_args__=(UniqueConstraint("user_id","legal_document_id","context","context_reference",name="uq_legal_acceptance_context"),)
