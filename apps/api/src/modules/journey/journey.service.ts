import { Injectable } from '@nestjs/common';
import axios from 'axios';
import { DatabaseService } from '../../common/database.service';
import { TransportMode } from '../../common/types';
import { AiService } from '../ai/ai.service';
import { StationsService } from '../stations/stations.service';
import { JourneyRequestDto } from './dto';

function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number) {
  const r = 6371;
  const dLat = (bLat - aLat) * Math.PI / 180;
  const dLon = (bLon - aLon) * Math.PI / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * Math.PI / 180) * Math.cos(bLat * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

const RAILWAY_JOURNEY_URL = process.env.RAILWAY_JOURNEY_URL ?? 'https://web-production-8fb77.up.railway.app/journey';

@Injectable()
export class JourneyService {
  constructor(
    private readonly stations: StationsService,
    private readonly ai: AiService,
    private readonly db: DatabaseService,
  ) {}

  async compute(dto: JourneyRequestDto) {
    const originLat = Number(dto.originLat ?? dto.lat_a);
    const originLon = Number(dto.originLon ?? dto.lon_a);
    const destinationLat = Number(dto.destinationLat ?? dto.lat_b);
    const destinationLon = Number(dto.destinationLon ?? dto.lon_b);
    const km = distanceKm(originLat, originLon, destinationLat, destinationLon);
    const nearest = await this.stations.findNearest(originLat, originLon);
    const bestStation = await this.stations.bestAvailable(originLat, originLon);
    const now = new Date();
    const context = {
      hour: Number(dto.hour ?? dto.heure ?? now.getHours()),
      dayOfWeek: now.getDay(),
      temperature: Number(dto.temperature ?? 20),
      precipitation: Number(dto.precipitation ?? 0),
      windSpeed: Number(dto.windSpeed ?? dto.wind_speed ?? 10),
      aqi: Number(dto.aqi ?? dto.indice_qualite ?? 3),
      trafficIndex: Number(dto.trafficIndex ?? 0.42),
    };

    const predict = await this.ai.predict({
      station_capacity: bestStation?.capacity ?? nearest?.capacity ?? 20,
      bikes_available: bestStation?.bikes_available ?? nearest?.bikes_available ?? 5,
      hour: context.hour,
      day_of_week: context.dayOfWeek,
      temperature: context.temperature,
      precipitation: context.precipitation,
      wind_speed: context.windSpeed,
      aqi: context.aqi,
    });

    const railway = await this.computeWithRailway(dto);
    if (railway) {
      return {
        ...railway,
        nearestStation: railway.nearestStation ?? nearest,
        bestStation: railway.bestStation ?? bestStation,
        prediction: railway.prediction ?? predict,
        context: railway.context ?? context,
        source: 'railway',
      };
    }

    const rawOptions = [
      this.option('bike', 'Velo', Math.round(km / 15 * 60), 0, 0.82, Math.min(1, predict.predicted_bikes_30min / 8)),
      this.option('walk', 'Marche', Math.round(km / 5 * 60), 0, 0.72, 1),
      this.option('transit', 'Transport', Math.round(km / 22 * 60 + 7), Math.round(km * 38), 0.78, 0.9),
      this.option('car', 'Voiture', Math.round(km / (32 - context.trafficIndex * 12) * 60 + 5), Math.round(km * 120), 0.74, 0.82),
    ];

    const options = await Promise.all(rawOptions.map(async (option) => {
      const score = await this.ai.score({
        duration_minutes: option.durationMinutes,
        co2_grams: option.co2Grams,
        comfort: option.comfort,
        availability: option.availability,
        weather_penalty: context.precipitation > 1 && ['bike', 'walk'].includes(option.mode) ? 0.7 : 0,
        pollution_penalty: context.aqi > 4 && ['bike', 'walk'].includes(option.mode) ? 0.6 : 0,
        traffic_index: option.mode === 'car' ? context.trafficIndex : 0,
      });

      return {
        ...option,
        score: score.score,
        scoreBreakdown: score.breakdown,
        timeline: this.timeline(option.mode, option.durationMinutes),
      };
    }));

    options.sort((a, b) => b.score - a.score);

    await this.db.query(
      `INSERT INTO trips (origin_lat, origin_lon, destination_lat, destination_lon, selected_mode, duration_minutes, co2_grams, ai_score)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [originLat, originLon, destinationLat, destinationLon, options[0].mode, options[0].durationMinutes, options[0].co2Grams, options[0].score],
    );

    return {
      recommended: options[0],
      nearestStation: nearest,
      bestStation,
      prediction: predict,
      options,
      context,
      distanceKm: Number(km.toFixed(2)),
    };
  }

  private option(mode: TransportMode, label: string, durationMinutes: number, co2Grams: number, comfort: number, availability: number) {
    return { mode, label, durationMinutes: Math.max(1, durationMinutes), co2Grams, comfort, availability };
  }

  private timeline(mode: TransportMode, duration: number) {
    const firstLeg = mode === 'bike' ? 'Marcher jusqu a la station' : mode === 'transit' ? 'Rejoindre l arret' : 'Depart';
    const mainLeg = mode === 'bike' ? 'Rouler sur axe securise' : mode === 'walk' ? 'Marcher' : mode === 'transit' ? 'Tram ou bus' : 'Conduire';
    return [
      { label: firstLeg, minutes: Math.max(2, Math.round(duration * 0.18)) },
      { label: mainLeg, minutes: Math.max(3, Math.round(duration * 0.68)) },
      { label: 'Arrivee et derniers metres', minutes: Math.max(1, Math.round(duration * 0.14)) },
    ];
  }

  private async computeWithRailway(dto: JourneyRequestDto) {
    try {
      const response = await axios.post(RAILWAY_JOURNEY_URL, dto, { timeout: 2500 });
      const data = response.data;

      if (data?.recommended && Array.isArray(data?.options)) {
        return data;
      }

      return null;
    } catch {
      return null;
    }
  }
}
