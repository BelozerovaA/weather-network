# Архитектура: разделение на Model / View / Controller

## Три слоя

**Model** — сущности предметной области и вся логика работы с данными
(валидация, расчёты, хранение, правила переходов статусов). Сюда входят:

- сущности: `Station`, `Device`, `Observation`, `Transmission`,
  `Verification`, `User`;
  **(ЛР №4)** `AnomalyMark`, `AuditLog`;
- сервисы: `StationService`, `DeviceService`, `ObservationService`,
  `TransmissionService`, `VerificationService`, `ReportService`;
  **(ЛР №4)** `AnomalyMarkService`, `AuditLogService`;
  **(ЛР №4)** `StationService` расширен методами `register(pending=)`, `confirm()`,
  `change_status()`, `list_pending()`;
- вспомогательные компоненты: `QualityControlEngine`, `ObservationSchedule`,
  `VerificationPolicy`, `MalfunctionLog`;
- доступ к данным: репозитории и `Database`;
  **(ЛР №4)** `AnomalyMarkRepository`, `AuditLogRepository`;
- валидаторы: `StationValidator`, `DeviceValidator`, `ObservationValidator`.

Именно в Model выполняются проверки. Например, валидаторы проверяют поля
станций, приборов и наблюдений; `QualityControlEngine` — диапазоны и
отклонение от соседних станций; `ObservationService` — активность станции,
уникальность срока и наличие исправного прибора с действующей поверкой;
`TransmissionService` выставляет признак задержанной передачи.
**(ЛР №4)** `AnomalyMarkService` проверяет, что обоснование аномалии не пустое;
`StationService.confirm()` и `change_status()` записывают событие в журнал аудита;
статус `PENDING` исключает станцию из сводных отчётов.

**View** — пользовательское представление. Реализован один класс
`ConsoleView`: заголовки, таблицы, сообщения об успехе и ошибках, ввод
строк, чисел, дат и выбор из списка. View не обращается к БД и не содержит
предметных правил — только разбор формата ввода и отображение.
**(ЛР №4)** Добавлены пункты меню: саморегистрация станции, подтверждение
станции, отметка аномалии, просмотр журнала аудита, список ожидающих станций.

**Controller** — связующее звено между вводом пользователя и Model:

- `MenuController` — выбор роли, меню действий, запрос данных через View,
  вызов `CenterController`, вывод результата;
- `CenterController` — единая точка входа к операциям Model с проверкой
  роли (`_require`); бизнес-правил и валидации в нём нет.
  **(ЛР №4)** Добавлены методы `confirm_station`, `mark_anomaly`,
  `list_anomaly_marks`, `list_audit_log`, `list_pending_stations`.
  Метод `_require` поддерживает роль `ANALYST` (синоптик-аналитик):
  разрешены только чтение и отметки аномалий, изменение наблюдений запрещено.

Controller не проверяет данные сам: при `ValueError` / `PermissionError`
из Model показывает сообщение через `view.error()`.

## Взаимодействие слоёв и интерфейсы

Поток вызовов:

**View → MenuController → CenterController → Service → Repository → БД**,
затем результат обратно во View.

View никогда не обращается к Model напрямую и не решает, корректны ли
данные с точки зрения предметной области.

Чтобы сервисы не зависели от конкретной реализации хранения и проверки,
введены два интерфейса:

- **`IRepository`** (`add`, `get`, `list`, `update`, `delete`) — реализуется
  `StationRepository`, `DeviceRepository`, `ObservationRepository` и др.;
  **(ЛР №4)** также `AnomalyMarkRepository`, `AuditLogRepository`;
  детали SQLite скрыты внутри репозиториев;
- **`IValidator`** (`validate(entity) → list[str]`) — реализуется
  `StationValidator`, `DeviceValidator`, `ObservationValidator`; сервисы
  вызывают валидаторы перед сохранением.

Сборка зависимостей (репозитории → сервисы → контроллеры) выполняется в
`bootstrap.build()` — composition root приложения.
**(ЛР №4)** В `bootstrap` подключены `AnomalyMarkService`, `AuditLogService`
и соответствующие репозитории.

## Диаграмма классов

![Диаграмма классов MVC](images/mvc_class_diagram.png)

*Рисунок — диаграмма классов MVC (исходная, ЛР №3).*

Пакеты `Model`, `View` и `Controller` на диаграмме подписаны и разделены
цветом фона. На диаграмме отражены фактические классы реализации:
`MenuController`, `CenterController`, `ConsoleView`, сервисы, репозитории,
валидаторы и интерфейсы `IRepository` / `IValidator`.

### Диаграмма классов после адаптации (ЛР №4)

![Диаграмма классов MVC после адаптации](images/диаграмма%20классов.png)

*Рисунок — диаграмма классов MVC после адаптации (ЛР №4).*

На адаптированной диаграмме дополнительно отражены:

- перечисления `Role` (значение `ANALYST`) и `StationStatus` (значение `PENDING`);
- сущности `AnomalyMark` и `AuditLog`;
- сервисы `AnomalyMarkService`, `AuditLogService` и расширенный `StationService`;
- репозитории `AnomalyMarkRepository`, `AuditLogRepository`, реализующие `IRepository`;
- новые методы `CenterController` (`confirm_station`, `mark_anomaly`,
  `list_audit_log`, `list_pending_stations`);
- связи Station 1 — 0..\* AuditLog («фиксирует») и
  Observation 1 — 0..\* AnomalyMark («помечается»).
