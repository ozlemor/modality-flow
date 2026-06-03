export type Station = {
  id: string;
  external_id: string;
  name: string;
  city: string;
  capacity: number;
  bikes_available: number;
  docks_available: number;
  status: string;
  health?: 'empty' | 'critical' | 'healthy' | 'high';
  availabilityRatio?: number;
  distance_meters?: number;
  lat: number;
  lon: number;
};

export type Parking = {
  id: string;
  external_id?: string;
  name: string;
  capacity: number;
  available_places: number;
  occupancyRatio?: number;
  lat: number;
  lon: number;
};

export type TamStop = {
  id?: string;
  stop_id?: string;
  name?: string;
  stop_name?: string;
  lat?: number;
  lon?: number;
  stop_lat?: number;
  stop_lon?: number;
  lines?: string[] | string;
  routes?: string[] | string;
  mode?: 'bus' | 'tram' | string;
};

export type TamRoute = {
  id?: string;
  route_id?: string;
  name?: string;
  route_short_name?: string;
  route_long_name?: string;
  type?: string;
  mode?: string;
  coordinates?: Array<[number, number]>;
};

export type JourneyOption = {
  mode: 'bike' | 'walk' | 'transit' | 'car';
  label: string;
  durationMinutes: number;
  co2Grams: number;
  score: number;
  comfort: number;
  availability: number;
  timeline: { label: string; minutes: number }[];
};

export type JourneyResponse = {
  recommended: JourneyOption;
  options: JourneyOption[];
  bestStation?: Station;
  nearestStation?: Station;
  distanceKm: number;
  prediction: {
    predicted_bikes_30min: number;
    confidence: number;
    model_version: string;
  };
};

export type EnvironmentContext = {
  hour: number;
  label: string;
  temperature: number;
  precipitation: number;
  windSpeed: number;
  aqi: number;
  trafficIndex: number;
  bikeComfort: 'low' | 'good' | 'high';
  recommendationReason: string;
  updatedAt: string;
};
