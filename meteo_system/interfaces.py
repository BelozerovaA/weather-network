"""
Абстракции Model: репозиторий и валидатор.

IRepository  — единый контракт для работы с хранилищем (SQLite, файлы и т.д.).
IValidator   — единый контракт для проверки корректности сущностей.

Благодаря абстракциям сервисы не зависят от конкретной реализации БД
и могут быть легко протестированы с подменами (mock).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

T = TypeVar("T")


class IRepository(ABC, Generic[T]):
    """CRUD-контракт для любой сущности."""

    @abstractmethod
    def add(self, entity: T) -> T:
        """Сохранить новую сущность, вернуть её с заполненным id."""
        ...

    @abstractmethod
    def get(self, entity_id: int) -> Optional[T]:
        """Найти сущность по первичному ключу."""
        ...

    @abstractmethod
    def list(self) -> List[T]:
        """Вернуть все сущности данного типа."""
        ...

    @abstractmethod
    def update(self, entity: T) -> None:
        """Обновить существующую сущность."""
        ...

    @abstractmethod
    def delete(self, entity_id: int) -> None:
        """Удалить сущность по id."""
        ...


class IValidator(ABC, Generic[T]):
    """Контракт валидации. Возвращает список текстовых ошибок (пустой = ок)."""

    @abstractmethod
    def validate(self, entity: T) -> List[str]:
        """
        Проверить сущность.
        :return: список сообщений об ошибках; пустой список означает успех.
        """
        ...
