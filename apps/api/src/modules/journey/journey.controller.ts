import { Body, Controller, Post } from '@nestjs/common';
import { JourneyRequestDto } from './dto';
import { JourneyService } from './journey.service';

@Controller('journey')
export class JourneyController {
  constructor(private readonly service: JourneyService) {}
  @Post() compute(@Body() body: JourneyRequestDto) { return this.service.compute(body); }
}
