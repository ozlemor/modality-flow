import { Logger, OnModuleInit } from '@nestjs/common';
import { SubscribeMessage, WebSocketGateway, WebSocketServer } from '@nestjs/websockets';
import { Server } from 'socket.io';
import { StationsService } from '../stations/stations.service';

@WebSocketGateway({ namespace: 'realtime', cors: { origin: '*' } })
export class RealtimeGateway implements OnModuleInit {
  private readonly logger = new Logger(RealtimeGateway.name);

  @WebSocketServer() server!: Server;

  constructor(private readonly stations: StationsService) {}

  onModuleInit() {
    setInterval(() => void this.broadcastStations(), 15000);
  }

  @SubscribeMessage('stations:refresh')
  async broadcastStations() {
    try {
      const stations = await this.stations.findAll();
      this.server.emit('stations:update', stations);
      return stations;
    } catch (error) {
      this.logger.warn(`Realtime stations refresh failed: ${(error as Error).message}`);
      return [];
    }
  }
}
