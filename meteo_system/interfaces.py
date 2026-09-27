"""Абстракции Model: репозиторий и валидатор."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

T = TypeVar("T")


class IRepository(ABC, Generic[T]):
    @abstractmethod
    def add(self, entity: T) -> T: ...

    @abstractmethod
    def get(self, entity_id: int) -> Optional[T]: ...

    @abstractmethod
    def list(self) -> List[T]: ...

    @abstractmethod
    def update(self, entity: T) -> None: ...

    @abstractmethod
    def delete(self, entity_id: int) -> None: ...


class IValidator(ABC, Generic[T]):
    @abstractmethod
    def validate(self, entity: T) -> List[str]:
        """Возвращает список ошибок; пустой список означает успешную проверку."""
        ...
