-- Схема БД сети метеорологических станций регионального центра.
-- Все запросы в репозиториях параметризованы (защита от SQL-инъекций).

-- Наблюдательные станции
CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,          -- уникальный код станции
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    type TEXT NOT NULL,                -- наземная / аэрологическая / ...
    status TEXT NOT NULL DEFAULT 'активна'
);

-- Измерительные приборы
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    serial_number TEXT NOT NULL UNIQUE,
    station_id INTEGER NOT NULL,
    last_verification TEXT,            -- ISO date
    next_verification TEXT,            -- ISO date
    status TEXT NOT NULL DEFAULT 'исправен',
    FOREIGN KEY (station_id) REFERENCES stations(id)
);

-- Результаты наблюдений
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id INTEGER NOT NULL,
    observation_time TEXT NOT NULL,    -- ISO datetime
    kind TEXT NOT NULL,                -- срочное / промежуточное
    parameters TEXT NOT NULL,          -- JSON: {"temperature": 12.5, ...}
    status TEXT NOT NULL DEFAULT 'создано',
    FOREIGN KEY (station_id) REFERENCES stations(id)
);

-- Факты передачи данных в центр
CREATE TABLE IF NOT EXISTS transmissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    transmission_time TEXT NOT NULL,   -- ISO datetime
    is_delayed INTEGER NOT NULL DEFAULT 0,  -- 0/1
    FOREIGN KEY (observation_id) REFERENCES observations(id)
);

-- Плановые и выполненные поверки приборов
CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    planned_date TEXT NOT NULL,        -- ISO date
    status TEXT NOT NULL DEFAULT 'запланировано',
    FOREIGN KEY (device_id) REFERENCES devices(id)
);
