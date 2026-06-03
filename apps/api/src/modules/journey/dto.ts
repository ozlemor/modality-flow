export class JourneyRequestDto {
  originLat!: number;
  originLon!: number;
  destinationLat!: number;
  destinationLon!: number;
  lat_a?: number;
  lon_a?: number;
  lat_b?: number;
  lon_b?: number;
  heure?: number;
  wind_speed?: number;
  indice_qualite?: number;
  temperature?: number;
  precipitation?: number;
  windSpeed?: number;
  aqi?: number;
  trafficIndex?: number;
  hour?: number;
}
