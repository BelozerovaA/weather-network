# Сеть метеорологических станций регионального центра

Учебный проект по МДК 03.01 «Моделирование и анализ ПО».

- Лабораторная работа №3 — прямое проектирование (от описания к моделям и коду).
- **Лабораторная работа №4** — анализ и адаптация системы к изменяющимся требованиям.

## Что это за система

Информационная система регионального метеорологического центра: реестр станций и приборов,
приём наблюдений по расписанию, контроль качества, учёт поверок, отчёты руководителя.

## Изменения по ЛР №4

Реализованы выбранные варианты адаптации (см. анализ требований):

| Требование | Как сделано |
|---|---|
| Саморегистрация станций | Статус `ожидает подтверждения` у Station; данные копятся, в сводные отчёты не входят |
| Подтверждение руководителем | Метод `StationService.confirm` + запись в AuditLog |
| Роль «Синоптик-аналитик» | `Role.ANALYST` — просмотр, отметки аномалий; **без** права менять наблюдения |
| Подтверждённая аномалия | Отдельная сущность `AnomalyMark` (исходное Observation не меняется) |
| Журнал аудита | Таблица `audit_log` в SQLite, индексы по станции и времени |

### Новые компоненты Model

- `models.StationStatus.PENDING`
- `models.Role.ANALYST`
- `models.AnomalyMark`, `models.AuditLog`
- `AnomalyMarkRepository`, `AuditLogRepository`
- `AnomalyMarkService`, `AuditLogService`
- Расширен `StationService`: `register(..., pending=)`, `confirm`, `change_status`, аудит

### Права ролей (Controller)

| Роль | Новые возможности |
|---|---|
| Руководитель | Саморегистрация, подтверждение станций, журнал аудита |
| Синоптик-аналитик | Просмотр всех данных, отметка аномалий, журнал аудита |
| Оператор | Журнал аудита (чтение) |

Валидация новых данных — в Model (пустой reason запрещён, статусы только из справочника).

## Основные сущности

| Сущность | Ключевые поля |
|---|---|
| Станция | code, name, latitude, longitude, type, **status** (в т.ч. «ожидает подтверждения») |
| Прибор | name, type, serial_number, station_id, last/next_verification, status |
| Наблюдение | station_id, observation_time, kind, parameters, status, flagged |
| Передача | observation_id, transmission_time, is_delayed |
| Поверка | device_id, planned_date, status |
| **AnomalyMark** | observation_id, author_id/name, reason, created_at |
| **AuditLog** | station_id, old/new_status, initiator, reason, created_at |

## Роли

| Роль | Возможности |
|---|---|
| Наблюдатель | Создаёт наблюдения и передачи |
| Оператор центра | Контроль качества, поверки, журнал сбоев |
| Руководитель | Станции/приборы, подтверждение, отчёты, аудит |
| **Синоптик-аналитик** | Просмотр, отметки аномалий, аудит (без изменения наблюдений) |

## Архитектура

**MVC**: Model (entities, validators, services, repositories) / View (ConsoleView) / Controller (CenterController + MenuController).

## Запуск

```bash
cd artifacts   # или корень проекта

python main.py              # интерактивное меню (meteo.db)
python main.py --demo       # демо на чистой БД
python main.py --db my.db   # другой файл БД
```

Требования: Python 3.10+, стандартная библиотека (SQLite).

## Структура

```
main.py
README.md
meteo_system/
  models.py          # сущности + справочники статусов/ролей
  validators.py
  quality.py
  schedule.py
  repositories.py    # + AnomalyMarkRepository, AuditLogRepository
  services.py        # + AnomalyMarkService, AuditLogService, confirm/PENDING
  reports.py
  db.py / schema.sql # + anomaly_marks, audit_log
  interfaces.py
  bootstrap.py
  controllers.py     # роль ANALYST, меню саморегистрации/аудита/аномалий
  views.py
```
