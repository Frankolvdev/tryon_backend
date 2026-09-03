from abc import ABC, abstractmethod
from sqlalchemy.orm import Session

class InfrastructureProviderAdapter(ABC):
    key: str
    label: str
    @abstractmethod
    def test(self, db: Session) -> dict: ...
    @abstractmethod
    def ensure_volume(self, db: Session) -> dict: ...
