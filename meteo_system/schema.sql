CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'активна'
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    serial_number TEXT NOT NULL UNIQUE,
    station_id INTEGER NOT NULL,
    last_verification TEXT,
    next_verification TEXT,
    status TEXT NOT NULL DEFAULT 'исправен',
    FOREIGN KEY (station_id) REFERENCES stations(id)
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id INTEGER NOT NULL,
    observation_time TEXT NOT NULL,
    kind TEXT NOT NULL,
    parameters TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'создано',
    FOREIGN KEY (station_id) REFERENCES stations(id)
);

CREATE TABLE IF NOT EXISTS transmissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    transmission_time TEXT NOT NULL,
    is_delayed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (observation_id) REFERENCES observations(id)
);

CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    planned_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'запланировано',
    FOREIGN KEY (device_id) REFERENCES devices(id)
);
