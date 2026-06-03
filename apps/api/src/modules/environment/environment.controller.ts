import { Controller, Get, Query } from '@nestjs/common';

type Condition = {
  hour: number;
  label: string;
  temperature: number;
  precipitation: number;
  windSpeed: number;
  aqi: number;
  trafficIndex: number;
};

function currentCondition(): Condition {
  const now = new Date();
  const hour = now.getHours();
  const rushHour = (hour >= 7 && hour <= 9) || (hour >= 17 && hour <= 19);
  const night = hour >= 22 || hour <= 5;
  const midday = hour >= 11 && hour <= 15;

  return {
    hour,
    label: night ? 'Nuit calme' : rushHour ? 'Heure de pointe' : midday ? 'Journee douce' : 'Trafic fluide',
    temperature: midday ? 24 : night ? 15 : 20,
    precipitation: 0,
    windSpeed: rushHour ? 14 : 9,
    aqi: rushHour ? 4 : 3,
    trafficIndex: rushHour ? 0.72 : night ? 0.18 : 0.38,
  };
}

@Controller()
export class EnvironmentController {
  @Get('environment/context')
  context() {
    const condition = currentCondition();
    const bikeComfort =
      condition.precipitation > 1 || condition.windSpeed > 28 || condition.aqi >= 5
        ? 'low'
        : condition.trafficIndex > 0.65
          ? 'high'
          : 'good';

    return {
      ...condition,
      bikeComfort,
      updatedAt: new Date().toISOString(),
      recommendationReason: this.reason(condition),
    };
  }

  @Get('meteo')
  meteo(@Query('date') date?: string) {
    const condition = currentCondition();
    return {
      date: date ?? new Date().toISOString().slice(0, 10),
      city: 'Montpellier',
      temperature: condition.temperature,
      precipitation: condition.precipitation,
      windSpeed: condition.windSpeed,
      summary: condition.precipitation > 1 ? 'Pluie' : condition.windSpeed > 24 ? 'Venteux' : 'Degage',
    };
  }

  @Get('aqi')
  aqi(@Query('date') date?: string) {
    const condition = currentCondition();
    return {
      date: date ?? new Date().toISOString().slice(0, 10),
      city: 'Montpellier',
      indice_qualite: condition.aqi,
      label: condition.aqi <= 2 ? 'Bon' : condition.aqi <= 4 ? 'Moyen' : 'Degrade',
    };
  }

  @Get('traffic')
  traffic() {
    const condition = currentCondition();
    return {
      index: condition.trafficIndex,
      label: condition.trafficIndex > 0.65 ? 'Charge' : condition.trafficIndex > 0.4 ? 'Modere' : 'Fluide',
      source: 'simulated-city-signal',
    };
  }

  @Get('co2/factors')
  co2Factors() {
    return {
      bike: 0,
      walk: 0,
      tram: 4,
      bus: 68,
      car: 120,
      unit: 'gCO2/km',
      source: 'ADEME-style factors',
    };
  }

  private reason(condition: Condition) {
    if (condition.precipitation > 1) return 'La pluie reduit le confort velo: priorite au transport public.';
    if (condition.aqi >= 5) return 'Pollution elevee: reduire marche et velo long, privilegier tram ou bus.';
    if (condition.trafficIndex > 0.65) return 'Trafic dense: le velo et le tram deviennent plus fiables que la voiture.';
    return 'Meteo stable, air correct et trafic fluide: le velo est une option rapide et bas carbone.';
  }
}
