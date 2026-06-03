CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS stations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  city TEXT NOT NULL DEFAULT 'Montpellier',
  capacity INT NOT NULL CHECK (capacity > 0),
  bikes_available INT NOT NULL DEFAULT 0 CHECK (bikes_available >= 0),
  docks_available INT NOT NULL DEFAULT 0 CHECK (docks_available >= 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'maintenance', 'offline')),
  operator TEXT NOT NULL DEFAULT 'city',
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  location GEOGRAPHY(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS parkings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  capacity INT NOT NULL CHECK (capacity > 0),
  available_places INT NOT NULL CHECK (available_places >= 0),
  operator TEXT NOT NULL DEFAULT 'city',
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  location GEOGRAPHY(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trips (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  origin_lat DOUBLE PRECISION NOT NULL,
  origin_lon DOUBLE PRECISION NOT NULL,
  destination_lat DOUBLE PRECISION NOT NULL,
  destination_lon DOUBLE PRECISION NOT NULL,
  selected_mode TEXT NOT NULL CHECK (selected_mode IN ('bike', 'walk', 'transit', 'car')),
  duration_minutes INT,
  co2_grams NUMERIC,
  ai_score NUMERIC,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS predictions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  station_id UUID REFERENCES stations(id) ON DELETE CASCADE,
  predicted_bikes INT NOT NULL,
  horizon_minutes INT NOT NULL DEFAULT 30,
  confidence NUMERIC,
  model_version TEXT NOT NULL DEFAULT 'heuristic-v1',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  station_id UUID REFERENCES stations(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  acknowledged_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS stations_location_idx ON stations USING GIST(location);
CREATE INDEX IF NOT EXISTS parkings_location_idx ON parkings USING GIST(location);
CREATE INDEX IF NOT EXISTS predictions_station_created_idx ON predictions(station_id, created_at DESC);
CREATE INDEX IF NOT EXISTS trips_created_idx ON trips(created_at DESC);

INSERT INTO stations (external_id, name, capacity, bikes_available, docks_available, lat, lon) VALUES
('MTP-001', 'Comedie', 24, 12, 12, 43.6086, 3.8795),
('MTP-002', 'Gare Saint-Roch', 30, 4, 26, 43.6046, 3.8806),
('MTP-003', 'Antigone', 20, 1, 19, 43.6079, 3.8908),
('MTP-004', 'Port Marianne', 28, 17, 11, 43.5989, 3.8981),
('MTP-005', 'Universite', 22, 8, 14, 43.6322, 3.8644),
('MTP-006', 'Hopitaux Facultes', 26, 21, 5, 43.6368, 3.8495),
('MTP-007', 'Rives du Lez', 18, 6, 12, 43.6034, 3.8974)
ON CONFLICT (external_id) DO UPDATE SET
  bikes_available = EXCLUDED.bikes_available,
  docks_available = EXCLUDED.docks_available,
  updated_at = NOW();

INSERT INTO parkings (external_id, name, capacity, available_places, lat, lon) VALUES
('PK-001', 'Parking Comedie', 600, 142, 43.6089, 3.8792),
('PK-002', 'Parking Gare', 420, 33, 43.6043, 3.881),
('PK-003', 'P+R Occitanie', 900, 511, 43.6348, 3.8487),
('PK-004', 'P+R Garcia Lorca', 480, 284, 43.5907, 3.8903)
ON CONFLICT (external_id) DO UPDATE SET
  available_places = EXCLUDED.available_places,
  updated_at = NOW();
