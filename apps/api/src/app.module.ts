import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { DatabaseService } from './common/database.service';
import { StationsController } from './modules/stations/stations.controller';
import { StationsService } from './modules/stations/stations.service';
import { ParkingsController } from './modules/parkings/parkings.controller';
import { ParkingsService } from './modules/parkings/parkings.service';
import { JourneyController } from './modules/journey/journey.controller';
import { JourneyService } from './modules/journey/journey.service';
import { DashboardController } from './modules/dashboard/dashboard.controller';
import { AiService } from './modules/ai/ai.service';
import { RealtimeGateway } from './modules/realtime/realtime.gateway';
import { PredictionsController } from './modules/predictions/predictions.controller';
import { PredictionsService } from './modules/predictions/predictions.service';
import { EnvironmentController } from './modules/environment/environment.controller';
import { TicketProxyController } from './modules/ticket/ticket-proxy.controller';
import { TamProxyController } from './modules/tam/tam-proxy.controller';

@Module({
  imports: [HttpModule],
  controllers: [StationsController, ParkingsController, JourneyController, DashboardController, PredictionsController, EnvironmentController, TicketProxyController, TamProxyController],
  providers: [DatabaseService, StationsService, ParkingsService, JourneyService, AiService, RealtimeGateway, PredictionsService],
})
export class AppModule {}
