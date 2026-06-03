import { Injectable } from '@nestjs/common';
import { DatabaseService } from '../../common/database.service';
import { Parking } from '../../common/types';

@Injectable()
export class ParkingsService {
  constructor(private readonly db: DatabaseService) {}

  async findAll(): Promise<Parking[]> {
    const res = await this.db.query<Parking>(`
      SELECT id, external_id, name, capacity, available_places, lat, lon, updated_at
      FROM parkings
      ORDER BY available_places DESC, name
    `);

    return res.rows.map((parking) => ({
      ...parking,
      occupancyRatio: Number(((Number(parking.capacity) - Number(parking.available_places)) / Math.max(Number(parking.capacity), 1)).toFixed(2)),
    }));
  }
}
