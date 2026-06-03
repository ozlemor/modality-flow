import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './api';
import { AddSegmentPayload, AlightTicketPayload, BoardTicketPayload } from '../features/ticket/ticket.types';

const DEVICE_TOKEN_KEY = 'modality_flow_device_token';

export async function getOrCreateDeviceToken() {
  const existing = await AsyncStorage.getItem(DEVICE_TOKEN_KEY);
  if (existing) return existing;

  const token = createUuid();
  await AsyncStorage.setItem(DEVICE_TOKEN_KEY, token);
  return token;
}

export async function boardTicket(payload: BoardTicketPayload) {
  return (await api.post('/ticket/board', payload)).data;
}

export async function addSegment(payload: AddSegmentPayload) {
  return (await api.post('/ticket/add_segment', payload)).data;
}

export async function alightTicket(payload: AlightTicketPayload) {
  return (await api.post('/ticket/alight', payload)).data;
}

export async function getTicket(ticketId: string) {
  return (await api.get(`/ticket/${ticketId}`)).data;
}

export async function recoverRefund(ticketId: string, terminalId = 'mobile-app') {
  return (await api.get(`/remboursement/${ticketId}/recuperer`, { params: { terminal_id: terminalId } })).data;
}

export async function getTicketStats() {
  return (await api.get('/billetterie/stats')).data;
}

function createUuid() {
  const cryptoObject = (globalThis as { crypto?: { randomUUID?: () => string; getRandomValues?: (array: Uint8Array) => Uint8Array } }).crypto;
  if (cryptoObject?.randomUUID) return cryptoObject.randomUUID();

  const bytes = new Uint8Array(16);
  cryptoObject?.getRandomValues?.(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0'));
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`;
}
