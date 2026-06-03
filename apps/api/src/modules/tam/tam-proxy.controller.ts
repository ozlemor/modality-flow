import { Controller, Get } from '@nestjs/common';
import axios from 'axios';

const RAILWAY_BASE_URL = process.env.RAILWAY_BASE_URL ?? 'https://web-production-8fb77.up.railway.app';
const FALLBACK_STOPS = [
  { id: 'tam-comedie', name: 'Comedie', lat: 43.6086, lon: 3.8795, mode: 'tram', lines: ['1', '2'] },
  { id: 'tam-gare', name: 'Gare Saint-Roch', lat: 43.6046, lon: 3.8806, mode: 'tram', lines: ['1', '2', '3', '4'] },
  { id: 'tam-antigone', name: 'Antigone', lat: 43.6079, lon: 3.8908, mode: 'tram', lines: ['1'] },
  { id: 'tam-port-marianne', name: 'Port Marianne', lat: 43.5989, lon: 3.8981, mode: 'tram', lines: ['1', '3'] },
];

const FALLBACK_ROUTES = [
  { id: 'tam-route-1', name: 'Ligne 1', mode: 'tram', coordinates: [[3.8795, 43.6086], [3.8908, 43.6079], [3.8981, 43.5989]] },
];

@Controller('tam')
export class TamProxyController {
  @Get('stops')
  async stops() {
    return this.getWithFallback('/tam/stops', FALLBACK_STOPS);
  }

  @Get('routes')
  async routes() {
    return this.getWithFallback('/tam/routes', FALLBACK_ROUTES);
  }

  private async getWithFallback(path: string, fallback: unknown) {
    try {
      const response = await axios.get(`${RAILWAY_BASE_URL}${path}`, { timeout: 5000 });
      return response.data;
    } catch {
      return fallback;
    }
  }
}
