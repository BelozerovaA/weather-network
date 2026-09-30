"""
View: консольное представление (ввод и вывод).

Отвечает ТОЛЬКО за обмен с пользователем: показать текст/таблицу и прочитать
введённое значение. Бизнес-правил и обращений к БД здесь нет — View лишь
разбирает формат ввода (число, дата) и переспрашивает, если текст не
удалось разобрать. Допустимость значений проверяет Model.

Функции ввода/вывода передаются в конструктор, поэтому View можно
тестировать подставными данными.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Sequence


class ConsoleView:
    """Консольный View: вывод сообщений и запрос данных."""

    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ):
        self._input = input_fn
        self._output = output_fn

    # ------------------------------ вывод ---------------------------------
    def header(self, text: str) -> None:
        """Заголовок секции."""
        self._output(f"\n--- {text} ---")

    def line(self, text: str = "") -> None:
        """Обычная строка вывода."""
        self._output(text)

    def success(self, text: str) -> None:
        self._output(f"✔ {text}")

    def error(self, text: str) -> None:
        """Сообщение об ошибке."""
        self._output(f"Ошибка: {text}")

    def table(self, headers: Sequence[str], rows: Sequence[Sequence]) -> None:
        """Простая таблица с выравниванием колонок."""
        if not rows:
            self._output("  (пусто)")
            return
        cells = [[str(c) for c in row] for row in rows]
        widths = [
            max(len(str(h)), *(len(r[i]) for r in cells))
            for i, h in enumerate(headers)
        ]
        self._output("  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
        self._output("  " + "  ".join("-" * w for w in widths))
        for row in cells:
            self._output("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths)))

    # ------------------------------ ввод ----------------------------------
    def ask(self, prompt: str, default: Optional[str] = None) -> str:
        """Строка; пустой ввод возвращает default (если он задан)."""
        suffix = f" [{default}]" if default not in (None, "") else ""
        while True:
            text = self._input(f"{prompt}{suffix}: ").strip()
            if text:
                return text
            if default is not None:
                return default
            self.error("значение не может быть пустым")

    def ask_float(self, prompt: str, default: Optional[float] = None) -> float:
        while True:
            text = self.ask(prompt, None if default is None else str(default))
            try:
                return float(text.replace(",", "."))
            except ValueError:
                self.error("введите число")

    def ask_optional_float(
        self, prompt: str, default: Optional[float] = None
    ) -> Optional[float]:
        """Число или пропуск (пустой ввод без default → None)."""
        shown = "" if default is None else f" [{default}]"
        while True:
            text = self._input(f"{prompt}{shown} (Enter — пропустить): ").strip()
            if not text:
                return default
            try:
                return float(text.replace(",", "."))
            except ValueError:
                self.error("введите число")

    def ask_int(self, prompt: str) -> int:
        while True:
            text = self.ask(prompt)
            try:
                return int(text)
            except ValueError:
                self.error("введите целое число")

    def ask_choice(self, prompt: str, options: Sequence[str]) -> int:
        """Выбор из списка; возвращает индекс (с нуля)."""
        for number, option in enumerate(options, 1):
            self._output(f"  {number}. {option}")
        while True:
            text = self.ask(prompt)
            if text.isdigit() and 1 <= int(text) <= len(options):
                return int(text) - 1
            self.error(f"выберите число от 1 до {len(options)}")

    def ask_yes_no(self, prompt: str, default: bool = True) -> bool:
        hint = "Д/н" if default else "д/Н"
        while True:
            text = self._input(f"{prompt} ({hint}): ").strip().lower()
            if not text:
                return default
            if text in ("д", "да", "y", "yes"):
                return True
            if text in ("н", "нет", "n", "no"):
                return False
            self.error("ответьте «д» или «н»")

    def ask_datetime(self, prompt: str, default: Optional[datetime] = None) -> datetime:
        """Дата и время: ГГГГ-ММ-ДД ЧЧ:ММ (или только дата)."""
        shown = default.strftime("%Y-%m-%d %H:%M") if default else None
        while True:
            text = self.ask(f"{prompt} (ГГГГ-ММ-ДД ЧЧ:ММ)", shown)
            try:
                return datetime.fromisoformat(text.replace("T", " "))
            except ValueError:
                self.error("неверный формат, пример: 2026-09-28 09:00")

    def ask_date(self, prompt: str, default: Optional[date] = None) -> str:
        """Дата ГГГГ-ММ-ДД; возвращает ISO-строку."""
        shown = default.isoformat() if default else None
        while True:
            text = self.ask(f"{prompt} (ГГГГ-ММ-ДД)", shown)
            try:
                return date.fromisoformat(text).isoformat()
            except ValueError:
                self.error("неверный формат, пример: 2026-09-28")
