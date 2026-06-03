import * as Location from 'expo-location';

export type MobilityPoint = {
  lat: number;
  lon: number;
  label: string;
};

export type EffectiveLocation = {
  location: MobilityPoint;
  realLocation?: MobilityPoint;
  usesTrackedCityLocation: boolean;
  isOutsideMontpellier: boolean;
  message: string;
  montpellierDistance?: {
    km: number;
    carHours: number;
    busHours: number;
    trainHours: number;
    label: string;
  };
};

export const MONTPELLIER_BOUNDS = {
  minLat: 43.52,
  maxLat: 43.7,
  minLon: 3.75,
  maxLon: 4.05,
};

export const TRACKED_CITY_ORIGIN: MobilityPoint = {
  lat: 43.6086,
  lon: 3.8795,
  label: 'Comedie - Montpellier',
};

export const TRACKED_CITY_DESTINATION: MobilityPoint = {
  lat: 43.5989,
  lon: 3.8981,
  label: 'Port Marianne',
};

export const TRACKED_LOCATION = TRACKED_CITY_ORIGIN;
export const TRACKED_DESTINATION = TRACKED_CITY_DESTINATION;

export function getTrackedMontpellierLocation() {
  return TRACKED_CITY_ORIGIN;
}

export function isInsideMontpellier(lat: number, lon: number) {
  return lat >= MONTPELLIER_BOUNDS.minLat &&
    lat <= MONTPELLIER_BOUNDS.maxLat &&
    lon >= MONTPELLIER_BOUNDS.minLon &&
    lon <= MONTPELLIER_BOUNDS.maxLon;
}

export function calculateDistanceKm(a: Pick<MobilityPoint, 'lat' | 'lon'>, b: Pick<MobilityPoint, 'lat' | 'lon'>) {
  const r = 6371;
  const dLat = (b.lat - a.lat) * Math.PI / 180;
  const dLon = (b.lon - a.lon) * Math.PI / 180;
  const x =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * Math.PI / 180) *
      Math.cos(b.lat * Math.PI / 180) *
      Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

export function estimateMontpellierAccess(realLocation: MobilityPoint) {
  const km = calculateDistanceKm(realLocation, TRACKED_CITY_ORIGIN);
  return {
    km: Math.round(km),
    carHours: roundHour(km / 90),
    busHours: roundHour(km / 70),
    trainHours: roundHour(km / 160),
    label: `Montpellier est a environ ${Math.round(km)} km - estimation`,
  };
}

export async function getUserLocation(): Promise<MobilityPoint> {
  const permission = await Location.requestForegroundPermissionsAsync();

  if (permission.status !== 'granted') {
    throw new Error('permission-denied');
  }

  const current = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.Balanced,
  });

  return {
    lat: current.coords.latitude,
    lon: current.coords.longitude,
    label: 'Ma position',
  };
}

export async function getEffectiveUserLocation(): Promise<EffectiveLocation> {
  try {
    const realLocation = await getUserLocation();

    if (isInsideMontpellier(realLocation.lat, realLocation.lon)) {
      return {
        location: realLocation,
        realLocation,
        usesTrackedCityLocation: false,
        isOutsideMontpellier: false,
        message: 'Ville suivie : Montpellier',
      };
    }

    return {
      location: TRACKED_CITY_ORIGIN,
      realLocation,
      usesTrackedCityLocation: true,
      isOutsideMontpellier: true,
      message: 'Ville suivie : Montpellier',
      montpellierDistance: estimateMontpellierAccess(realLocation),
    };
  } catch {
    return {
      location: TRACKED_CITY_ORIGIN,
      usesTrackedCityLocation: true,
      isOutsideMontpellier: false,
      message: 'Ville suivie : Montpellier',
    };
  }
}

export const getEffectiveLocation = getEffectiveUserLocation;

function roundHour(hours: number) {
  return Math.round(hours * 10) / 10;
}
