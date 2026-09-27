# Архитектура: разделение на Model / View / Controller

## Три слоя

**Model** — классы предметной области и логика работы с данными (валидация,
расчёты, хранение, правила переходов между статусами): `Station`,
`Instrument`, `Observation`, `VerificationRecord`, `FailureLog`, `Report`.
Именно здесь проверяются данные — например, `Observation.setValue()`
проверяет диапазон значения, `Instrument.checkCalibrationDue()` определяет
просроченность поверки, `Station.registerInstrument()` проверяет
совместимость прибора со станцией.

**View** — пользовательское представление: `ConsoleMenu` (консольное меню),
`ObservationEntryForm` и `StationRegistrationForm` (формы ввода),
`ReportView` (вывод отчётов и списков), `ErrorMessageView` (вывод сообщений
об ошибках).

**Controller** — связующее звено, принимает действия пользователя и
обновляет View: `ObservationController`, `StationController`,
`VerificationController`, `ReportController`. Controller не проверяет
данные сам — он только передаёт их в Model и, в зависимости от результата,
показывает нужный View (подтверждение или ошибку).

## Взаимодействие слоёв и интерфейсы

Поток вызовов: **View → Controller → Model → Controller → View**. View
никогда не обращается к Model напрямую и не принимает решений о
корректности данных.

Чтобы Model не зависел от конкретной реализации хранения и проверки,
введены два интерфейса:

- **`IRepository`** (`save`, `findById`, `findAll`) — реализуется классами
  хранения `Station` и `Observation`; Controller работает с данными только
  через этот интерфейс, поэтому способ хранения можно поменять, не трогая
  Model и Controller;
- **`IValidator`** (`validate(data)`) — реализуется самими доменными
  классами (`Observation`, `Instrument`), которые проверяют собственные
  данные при изменении состояния.

## Диаграмма классов

![Диаграмма классов MVC](images/mvc_class_diagram.png)

Пакеты `Model`, `View` и `Controller` на диаграмме подписаны и разделены
цветом фона.
