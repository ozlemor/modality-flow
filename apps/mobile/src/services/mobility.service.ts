import { api } from './api';
import { EnvironmentContext, JourneyResponse, Parking, Station, TamRoute, TamStop } from '../types';

export type AqiSignal = {
  indice_qualite?: number;
  aqi?: number;
  label?: string;
  city?: string;
  today?: {
    indice_qualite?: number;
    libelle_qualite?: string | null;
  };
};

export type WeatherSignal = {
  temperature: number;
  precipitation: number;
  windSpeed?: number;
  wind_speed?: number;
  summary?: string;
  today?: {
    temperature_max?: number;
    temperature_min?: number | null;
    precipitation_sum?: number;
    wind_speed_max?: number;
    weather_code?: number;
  };
};

export type JourneyRequest = {
  lat_a: number;
  lon_a: number;
  lat_b: number;
  lon_b: number;
  heure: number;
  precipitation: number;
  temperature: number;
  wind_speed: number;
  indice_qualite: number;
};

export async function getStations() {
  const data = (await api.get<Array<Station | any> | { stations?: Array<Station | any>; data?: Array<Station | any> }>('/stations')).data;
  const stations = Array.isArray(data) ? data : data.stations ?? data.data ?? [];
  const normalized = stations.map(normalizeStation);
  const valid = normalized.filter((station) => Number.isFinite(station.lat) && Number.isFinite(station.lon));
  console.log(`Stations loaded: ${stations.length}`);
  console.log(`Valid stations: ${valid.length}`);
  console.log(`Invalid stations: ${stations.length - valid.length}`);
  return valid;
}

export async function getParkings() {
  const data = (await api.get<Array<Parking | any> | { parkings?: Array<Parking | any>; data?: Array<Parking | any> }>('/parkings')).data;
  const parkings = Array.isArray(data) ? data : data.parkings ?? data.data ?? [];
  const normalized = parkings.map(normalizeParking);
  const valid = normalized.filter((parking) => Number.isFinite(parking.lat) && Number.isFinite(parking.lon));
  console.log(`Parkings loaded: ${parkings.length}`);
  console.log(`Valid parkings: ${valid.length}`);
  console.log(`Invalid parkings: ${parkings.length - valid.length}`);
  return valid;
}

export async function getTamStops() {
  const data = (await api.get<TamStop[] | { stops?: TamStop[] }>('/tam/stops')).data;
  const stops = Array.isArray(data) ? data : data.stops ?? [];
  console.log(`TAM stops loaded: ${stops.length}`);
  return stops;
}

export async function getTamRoutes() {
  const data = (await api.get<TamRoute[] | { routes?: TamRoute[] }>('/tam/routes')).data;
  return Array.isArray(data) ? data : data.routes ?? [];
}

export async function getAqi() {
  const data = (await api.get<AqiSignal>('/aqi')).data;
  return {
    ...data,
    indice_qualite: data.indice_qualite ?? data.today?.indice_qualite ?? data.aqi,
    label: data.label ?? data.today?.libelle_qualite ?? undefined,
  };
}

export async function getWeather() {
  const data = (await api.get<WeatherSignal>('/meteo')).data;
  return {
    ...data,
    temperature: data.temperature ?? data.today?.temperature_max ?? 20,
    precipitation: data.precipitation ?? data.today?.precipitation_sum ?? 0,
    windSpeed: data.windSpeed ?? data.wind_speed ?? data.today?.wind_speed_max ?? 10,
  };
}

export async function getEnvironmentContext() {
  return (await api.get<EnvironmentContext>('/environment/context')).data;
}

export async function getCo2Factors() {
  return (await api.get('/co2/factors')).data as Record<string, number | string>;
}

export async function calculateJourney(payload: JourneyRequest) {
  return (await api.post<JourneyResponse>('/journey', payload)).data;
}

export async function predictStation(stationId: string) {
  return (await api.post(`/stations/${stationId}/predict`)).data;
}

function normalizeStation(raw: Station | any): Station {
  const capacity = Number(raw.capacity ?? raw.capacite ?? 0);
  const bikes = Number(raw.bikes_available ?? raw.velos_disponibles ?? 0);
  const availabilityRatio = Number.isFinite(Number(raw.availabilityRatio))
    ? Number(raw.availabilityRatio)
    : Number.isFinite(Number(raw.taux_disponibilite))
      ? Number(raw.taux_disponibilite) / 100
      : bikes / Math.max(capacity, 1);

  return {
    id: String(raw.id ?? raw.station_id ?? raw.external_id),
    external_id: String(raw.external_id ?? raw.station_id ?? raw.id),
    name: String(raw.name ?? raw.nom ?? 'Station velo'),
    city: String(raw.city ?? raw.ville ?? 'Montpellier'),
    capacity,
    bikes_available: bikes,
    docks_available: Number(raw.docks_available ?? raw.places_libres ?? Math.max(0, capacity - bikes)),
    status: String(raw.status ?? (raw.is_renting === false ? 'inactive' : 'active')),
    health: raw.health,
    availabilityRatio,
    distance_meters: raw.distance_meters,
    lat: Number(raw.lat),
    lon: Number(raw.lon),
  };
}

function normalizeParking(raw: Parking | any): Parking {
  const capacity = Number(raw.capacity ?? raw.capacite ?? 0);
  const available = Number(raw.available_places ?? raw.places_disponibles ?? raw.disponible ?? 0);
  const occupancyRatio = Number.isFinite(Number(raw.occupancyRatio))
    ? Number(raw.occupancyRatio)
    : Number.isFinite(Number(raw.taux_occupation))
      ? Number(raw.taux_occupation)
      : capacity ? 1 - available / capacity : 0;

  return {
    id: String(raw.id ?? raw.parking_id ?? raw.external_id),
    external_id: raw.external_id ?? raw.parking_id,
    name: String(raw.name ?? raw.nom ?? 'Parking'),
    capacity,
    available_places: available,
    occupancyRatio,
    lat: Number(raw.lat),
    lon: Number(raw.lon),
  };
}
