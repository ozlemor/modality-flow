export type TransportMode = 'bike' | 'walk' | 'transit' | 'car';

export interface Station {
  id: string;
  external_id: string;
  name: string;
  city: string;
  capacity: number;
  bikes_available: number;
  docks_available: number;
  status: string;
  lat: number;
  lon: number;
  updated_at: string;
  distance_meters?: number;
}

export interface Parking {
  id: string;
  external_id: string;
  name: string;
  capacity: number;
  available_places: number;
  lat: number;
  lon: number;
  updated_at: string;
}
