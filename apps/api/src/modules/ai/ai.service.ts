import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class AiService {
  constructor(private readonly http: HttpService) {}

  async predict(payload: any) {
    const url = `${process.env.AI_SERVICE_URL ?? 'http://localhost:8000'}/predict`;
    try {
      const res = await firstValueFrom(this.http.post(url, payload));
      return res.data;
    } catch {
      return {
        predicted_bikes_30min: Math.max(0, Math.min(payload.station_capacity, payload.bikes_available - (payload.precipitation > 1 ? 2 : 0))),
        confidence: 0.55,
        model_version: 'fallback-api',
      };
    }
  }

  async score(payload: any) {
    const url = `${process.env.AI_SERVICE_URL ?? 'http://localhost:8000'}/score`;
    try {
      const res = await firstValueFrom(this.http.post(url, payload));
      return res.data;
    } catch {
      const score = 100 - payload.duration_minutes * 0.35 - payload.co2_grams * 0.03 + payload.comfort * 10 + payload.availability * 15;
      return { score: Number(Math.max(0, Math.min(100, score)).toFixed(2)), breakdown: { fallback: true } };
    }
  }
}
