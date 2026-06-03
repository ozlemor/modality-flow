import { MobilityPoint } from '../../services/location.service';

export type TicketMode = 'velo' | 'tram' | 'bus' | 'marche' | 'voiture';

export type TicketSegment = {
  mode: TicketMode;
  startedAt: string;
  stationId?: string;
  label: string;
};

export type FlowTicket = {
  ticket_id: string;
  status: 'active' | 'finished';
  mode: TicketMode;
  startTime: string;
  endTime?: string;
  startLocation: MobilityPoint;
  endLocation?: MobilityPoint;
  qr_data?: string;
  segments: TicketSegment[];
  pricePaid?: number;
  refundAvailable?: number;
  refundRecovered?: boolean;
  co2SavedKg?: number;
  xpEarned?: number;
  raw?: unknown;
};

export type BoardTicketPayload = {
  device_token: string;
  mode: TicketMode;
  station_id?: string;
  terminal_id: string;
  lat: number;
  lon: number;
};

export type AddSegmentPayload = BoardTicketPayload & {
  ticket_id: string;
};

export type AlightTicketPayload = {
  ticket_id: string;
  device_token: string;
  station_id?: string;
  terminal_id: string;
  lat: number;
  lon: number;
  distance_reelle_km: number;
};
