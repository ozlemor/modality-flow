# Modality Flow

Application mobile de mobilite urbaine intelligente: React Native Expo + NestJS + FastAPI IA + PostgreSQL/PostGIS + Redis + Mapbox.

## Lancer le projet

```bash
docker compose up --build
```

Dans un second terminal:

```bash
npm --workspace apps/mobile run start
```

## Ports

- API NestJS via Docker: http://localhost:3001/api/v1
- IA FastAPI: http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Variables utiles

- `EXPO_PUBLIC_API_URL=http://localhost:3001`
- `EXPO_PUBLIC_MAPBOX_TOKEN=...`

## Architecture

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## API Endpoints Railway

Base URL historique Railway: `https://modality-flow.railway.app`

### ML Prediction

`POST /stations/{station_id}/predict`

### Stations real-time

`GET /stations`

### CO2 Route

`POST /route/co2`
