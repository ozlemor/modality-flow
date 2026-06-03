import { Body, Controller, Get, Param, Post, Query } from '@nestjs/common';
import axios from 'axios';

const RAILWAY_BASE_URL = process.env.RAILWAY_BASE_URL ?? 'https://web-production-8fb77.up.railway.app';
const FORBIDDEN_ENDPOINT_PREFIXES = ['/lille'];

@Controller()
export class TicketProxyController {
  @Post('ticket/board')
  board(@Body() body: unknown) {
    return this.forward('post', '/ticket/board', body);
  }

  @Post('ticket/add_segment')
  addSegment(@Body() body: unknown) {
    return this.forward('post', '/ticket/add_segment', body);
  }

  @Post('ticket/alight')
  alight(@Body() body: unknown) {
    return this.forward('post', '/ticket/alight', body);
  }

  @Get('ticket/:ticketId')
  getTicket(@Param('ticketId') ticketId: string) {
    return this.forward('get', `/ticket/${encodeURIComponent(ticketId)}`);
  }

  @Get('remboursement/:ticketId/recuperer')
  recoverRefund(@Param('ticketId') ticketId: string, @Query('terminal_id') terminalId = 'mobile-app') {
    return this.forward('get', `/remboursement/${encodeURIComponent(ticketId)}/recuperer?terminal_id=${encodeURIComponent(terminalId)}`);
  }

  @Get('billetterie/stats')
  stats() {
    return this.forward('get', '/billetterie/stats');
  }

  private async forward(method: 'get' | 'post', path: string, body?: unknown) {
    if (FORBIDDEN_ENDPOINT_PREFIXES.some((prefix) => path.startsWith(prefix))) {
      throw new Error(`Forbidden mobility endpoint blocked: ${path}`);
    }

    const url = `${RAILWAY_BASE_URL}${path}`;
    const response = method === 'get'
      ? await axios.get(url, { timeout: 8000 })
      : await axios.post(url, body, { timeout: 8000 });

    return response.data;
  }
}
