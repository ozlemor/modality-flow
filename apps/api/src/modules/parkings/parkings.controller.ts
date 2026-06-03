import { Controller, Get } from '@nestjs/common';
import { ParkingsService } from './parkings.service';

@Controller('parkings')
export class ParkingsController {
  constructor(private readonly service: ParkingsService) {}
  @Get() findAll() { return this.service.findAll(); }
}
