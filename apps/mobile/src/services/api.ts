import axios from 'axios';
import { io } from 'socket.io-client';

export const FORBIDDEN_ENDPOINT_PREFIXES = ['/lille'];
export const OFFICIAL_API_URL = 'https://web-production-8fb77.up.railway.app';

function resolveApiUrl() {
  const configured = process.env.EXPO_PUBLIC_API_URL;
  return configured ?? OFFICIAL_API_URL;
}

const API_URL = resolveApiUrl();

export const api = axios.create({
  baseURL: API_URL,
  timeout: 10000,
});

api.interceptors.request.use((config) => {
  const url = config.url ?? '';
  const path = url.startsWith('http') ? new URL(url).pathname : url;
  const forbidden = FORBIDDEN_ENDPOINT_PREFIXES.some((prefix) => path.startsWith(prefix));

  if (forbidden) {
    console.error(`[Modality Flow] Endpoint interdit bloque: ${url}`);
    throw new Error(`Endpoint interdit: ${url}`);
  }

  return config;
});

export const realtime = io(`${API_URL}/realtime`, {
  transports: ['websocket'],
  autoConnect: false,
});
