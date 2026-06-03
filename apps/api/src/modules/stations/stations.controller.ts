import { Controller, Get, Param, Query } from '@nestjs/common';
import { StationsService } from './stations.service';

@Controller('stations')
export class StationsController {
  constructor(private readonly service: StationsService) {}

  @Get()
  findAll() { return this.service.findAll(); }

  @Get('nearest')
  nearest(@Query('lat') lat: string, @Query('lon') lon: string) {
    return this.service.findNearest(Number(lat), Number(lon));
  }

  @Get('best')
  best(@Query('lat') lat: string, @Query('lon') lon: string) {
    return this.service.bestAvailable(Number(lat), Number(lon));
  }

  @Get(':id')
  findOne(@Param('id') id: string) { return this.service.findOne(id); }
}
