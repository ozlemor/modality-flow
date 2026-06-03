import { Injectable } from '@nestjs/common';
import { DatabaseService } from '../../common/database.service';
import { Station } from '../../common/types';

@Injectable()
export class StationsService {
  constructor(private readonly db: DatabaseService) {}

  async findAll(): Promise<Station[]> {
    const res = await this.db.query<Station>(`
      SELECT id, external_id, name, city, capacity, bikes_available, docks_available, status, lat, lon, updated_at
      FROM stations
      ORDER BY
        CASE
          WHEN bikes_available = 0 THEN 3
          WHEN bikes_available <= 2 THEN 2
          ELSE 1
        END,
        name
    `);
    return res.rows.map(this.enrichStation);
  }

  async findOne(id: string): Promise<Station | null> {
    const res = await this.db.query<Station>(`
      SELECT id, external_id, name, city, capacity, bikes_available, docks_available, status, lat, lon, updated_at
      FROM stations
      WHERE id::text = $1 OR external_id = $1
      LIMIT 1
    `, [id]);
    return res.rows[0] ? this.enrichStation(res.rows[0]) : null;
  }

  async findNearest(lat: number, lon: number): Promise<Station | null> {
    const res = await this.db.query<Station>(`
      SELECT id, external_id, name, city, capacity, bikes_available, docks_available, status, lat, lon, updated_at,
        ST_Distance(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) AS distance_meters
      FROM stations
      ORDER BY location <-> ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
      LIMIT 1
    `, [lat, lon]);
    return res.rows[0] ? this.enrichStation(res.rows[0]) : null;
  }

  async bestAvailable(lat: number, lon: number): Promise<Station | null> {
    const res = await this.db.query<Station>(`
      SELECT id, external_id, name, city, capacity, bikes_available, docks_available, status, lat, lon, updated_at,
        ST_Distance(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) AS distance_meters
      FROM stations
      WHERE status = 'active' AND bikes_available > 0
      ORDER BY (ST_Distance(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) / 120) - (bikes_available * 7) ASC
      LIMIT 1
    `, [lat, lon]);
    return res.rows[0] ? this.enrichStation(res.rows[0]) : null;
  }

  private enrichStation(station: Station) {
    const ratio = Number(station.bikes_available) / Math.max(Number(station.capacity), 1);
    return {
      ...station,
      health: ratio === 0 ? 'empty' : ratio <= 0.12 ? 'critical' : ratio >= 0.7 ? 'high' : 'healthy',
      availabilityRatio: Number(ratio.toFixed(2)),
    };
  }
}
