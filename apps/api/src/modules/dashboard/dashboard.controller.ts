import { Controller, Get } from '@nestjs/common';
import { DatabaseService } from '../../common/database.service';

@Controller('dashboard')
export class DashboardController {
  constructor(private readonly db: DatabaseService) {}

  @Get('kpi')
  async kpi() {
    const bikes = await this.db.query('SELECT COALESCE(SUM(bikes_available),0)::int AS total FROM stations');
    const stations = await this.db.query('SELECT COUNT(*)::int AS total FROM stations');
    const critical = await this.db.query('SELECT COUNT(*)::int AS total FROM stations WHERE bikes_available <= 2');
    const parkings = await this.db.query('SELECT COALESCE(SUM(available_places),0)::int AS total FROM parkings');
    const trips = await this.db.query("SELECT COUNT(*)::int AS total FROM trips WHERE created_at > NOW() - INTERVAL '24 hours'");
    const co2 = await this.db.query("SELECT COALESCE(SUM(GREATEST(0, 120 - co2_grams)),0)::int AS total FROM trips WHERE created_at > NOW() - INTERVAL '24 hours'");

    return {
      bikesAvailable: bikes.rows[0].total,
      stations: stations.rows[0].total,
      criticalStations: critical.rows[0].total,
      parkingPlaces: parkings.rows[0].total,
      aqi: 3,
      tripsToday: trips.rows[0].total,
      co2SavedGrams: co2.rows[0].total,
      status: Number(critical.rows[0].total) > 2 ? 'watch' : 'stable',
    };
  }
}
