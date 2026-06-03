import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { PredictionsService } from './predictions.service';

@Controller('predict')
export class PredictionsController {
  constructor(private readonly service: PredictionsService) {}

  @Post()
  predict(@Body() body: { stationId?: string; externalId?: string; horizonMinutes?: number }) {
    return this.service.predictForStation(body.stationId ?? body.externalId, body.horizonMinutes ?? 30);
  }

  @Get(':stationId')
  predictByStation(@Param('stationId') stationId: string) {
    return this.service.predictForStation(stationId, 30);
  }
}
