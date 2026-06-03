import { Injectable, NotFoundException } from '@nestjs/common';
import { DatabaseService } from '../../common/database.service';
import { AiService } from '../ai/ai.service';
import { StationsService } from '../stations/stations.service';

@Injectable()
export class PredictionsService {
  constructor(
    private readonly db: DatabaseService,
    private readonly ai: AiService,
    private readonly stations: StationsService,
  ) {}

  async predictForStation(stationId?: string, horizonMinutes = 30) {
    if (!stationId) {
      throw new NotFoundException('stationId or externalId is required');
    }

    const station = await this.stations.findOne(stationId);
    if (!station) {
      throw new NotFoundException('Station not found');
    }

    const now = new Date();
    const prediction = await this.ai.predict({
      station_capacity: Number(station.capacity),
      bikes_available: Number(station.bikes_available),
      hour: now.getHours(),
      day_of_week: now.getDay(),
      temperature: 20,
      precipitation: 0,
      wind_speed: 10,
      aqi: 3,
    });

    await this.db.query(
      `INSERT INTO predictions (station_id, predicted_bikes, horizon_minutes, confidence)
       VALUES ($1, $2, $3, $4)`,
      [station.id, prediction.predicted_bikes_30min, horizonMinutes, prediction.confidence],
    );

    return {
      station,
      horizonMinutes,
      predictedBikes: prediction.predicted_bikes_30min,
      confidence: prediction.confidence,
      modelVersion: prediction.model_version ?? 'heuristic-v1',
    };
  }
}
