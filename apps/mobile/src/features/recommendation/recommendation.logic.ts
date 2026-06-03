import { EnvironmentContext, JourneyOption, Station } from '../../types';
import { TimeContext } from './timeContext.logic';

export { getTimeContext } from './timeContext.logic';

export type LocalMode = JourneyOption['mode'];

export type LocalRecommendation = {
  mode: LocalMode;
  label: string;
  icon: string;
  score: number;
  durationMinutes: number;
  co2SavedKg: number;
  reason: string;
  reasons: string[];
  options: Array<{
    mode: LocalMode;
    label: string;
    icon: string;
    score: number;
    durationMinutes: number;
    co2SavedKg: number;
    reason: string;
  }>;
};

const MODE_META: Record<LocalMode, { label: string; icon: string; duration: number; co2: number }> = {
  bike: { label: 'Velo recommande', icon: '🚲', duration: 12, co2: 1.4 },
  walk: { label: 'Marche conseillee', icon: '🚶', duration: 28, co2: 1.0 },
  transit: { label: 'Tram recommande', icon: '🚋', duration: 16, co2: 0.8 },
  car: { label: 'Voiture possible', icon: '🚗', duration: 18, co2: 0 },
};

export function scoreMobility({
  environment,
  timeContext,
  bikesAvailable,
}: {
  environment?: EnvironmentContext;
  timeContext: TimeContext;
  bikesAvailable: number;
}) {
  const precipitation = environment?.precipitation ?? 0;
  const windSpeed = environment?.windSpeed ?? 10;
  const temperature = environment?.temperature ?? 20;
  const aqi = environment?.aqi ?? 3;
  const trafficIndex = environment?.trafficIndex ?? 0.42;
  const goodWeather = temperature >= 10 && temperature <= 28 && precipitation <= 1 && windSpeed <= 35;
  const heavyRain = precipitation > 2;
  const strongWind = windSpeed > 35;
  const cold = temperature < 5;
  const highAqi = aqi >= 4;
  const highTraffic = trafficIndex > 0.6;

  const scores: Record<LocalMode, number> = {
    bike: 70,
    walk: 60,
    transit: 65,
    car: 50,
  };

  const reasons: string[] = [];

  if (goodWeather) {
    scores.bike += 15;
    scores.walk += 10;
    reasons.push('meteo agreable');
  }

  if (heavyRain) {
    scores.bike -= 30;
    scores.walk -= 20;
    scores.transit += 15;
    reasons.push('pluie forte, le tram est plus confortable');
  }

  if (strongWind) {
    scores.bike -= 15;
    reasons.push('vent fort, le velo fatigue plus');
  }

  if (cold) {
    scores.bike -= 12;
    scores.walk -= 10;
    scores.transit += 8;
    reasons.push('temperature basse');
  }

  if (highAqi) {
    scores.bike -= 15;
    scores.walk -= 20;
    scores.transit += 10;
    reasons.push('air moyen, transport public plus doux');
  } else {
    reasons.push('air correct');
  }

  if (timeContext.isRushHour) {
    scores.car -= 25;
    scores.bike += 10;
    scores.transit += 10;
    reasons.push('heure de pointe');
  }

  if (highTraffic) {
    scores.car -= 15;
    scores.transit += 5;
    reasons.push('trafic eleve');
  }

  if (bikesAvailable > 0) {
    scores.bike += 20;
    reasons.push('velos disponibles pres de vous');
  } else {
    scores.bike -= 50;
    scores.transit += 8;
    reasons.push('pas assez de velos disponibles');
  }

  if (timeContext.isNight) {
    scores.walk -= 25;
    scores.bike -= 10;
    scores.transit += 10;
    reasons.push('nuit, securite prioritaire');
  }

  return scores;
}

export function buildLocalRecommendation({
  environment,
  timeContext,
  stations,
}: {
  environment?: EnvironmentContext;
  timeContext: TimeContext;
  stations?: Station[];
}): LocalRecommendation {
  const safeStations = Array.isArray(stations) ? stations : [];
  const bikesAvailable = safeStations.reduce((sum, station) => sum + station.bikes_available, 0) || 8;
  const scores = scoreMobility({ environment, timeContext, bikesAvailable });
  const sorted = (Object.entries(scores) as Array<[LocalMode, number]>).sort((a, b) => b[1] - a[1]);
  const bestMode = sorted[0][0];
  const meta = MODE_META[bestMode];
  const reason = buildReason(bestMode, environment, timeContext, bikesAvailable);

  return {
    mode: bestMode,
    label: meta.label,
    icon: meta.icon,
    score: Math.max(0, Math.min(100, Math.round(scores[bestMode]))),
    durationMinutes: meta.duration,
    co2SavedKg: meta.co2,
    reason,
    reasons: reason.split(', '),
    options: sorted.map(([mode, score]) => ({
      mode,
      label: MODE_META[mode].label.replace(' recommande', '').replace(' conseillee', ''),
      icon: MODE_META[mode].icon,
      score: Math.max(0, Math.min(100, Math.round(score))),
      durationMinutes: MODE_META[mode].duration,
      co2SavedKg: MODE_META[mode].co2,
      reason: buildReason(mode, environment, timeContext, bikesAvailable),
    })),
  };
}

function buildReason(mode: LocalMode, environment: EnvironmentContext | undefined, timeContext: TimeContext, bikesAvailable: number) {
  const precipitation = environment?.precipitation ?? 0;
  const temperature = environment?.temperature ?? 20;
  const aqi = environment?.aqi ?? 3;
  const trafficIndex = environment?.trafficIndex ?? 0.42;

  if (precipitation > 2 && mode === 'transit') return 'Il pleut, le tram est plus confortable.';
  if (aqi >= 4 && mode === 'transit') return 'Air moyen aujourd hui, mieux vaut un trajet doux.';
  if (timeContext.isRushHour && trafficIndex > 0.55 && mode !== 'car') return 'Heure de pointe, on evite la voiture.';
  if (mode === 'bike' && bikesAvailable > 0 && temperature >= 10 && temperature <= 28) return 'Bonne meteo, air correct et velos disponibles pres de vous.';
  if (mode === 'walk') return 'Distance courte et bon moment pour bouger.';
  if (mode === 'car') return 'Option gardee en secours, moins interessante pour votre impact.';
  return 'C est le meilleur equilibre maintenant.';
}
