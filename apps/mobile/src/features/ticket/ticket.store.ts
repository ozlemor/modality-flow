import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { FlowTicket } from './ticket.types';

const ACTIVE_TICKET_KEY = 'modality_flow_active_ticket';
const HISTORY_KEY = 'modality_flow_ticket_history';

type TicketState = {
  activeTicket?: FlowTicket;
  lastTicket?: FlowTicket;
  hydrated: boolean;
  hydrate: () => Promise<void>;
  setActiveTicket: (ticket: FlowTicket) => Promise<void>;
  finishTicket: (ticket: FlowTicket) => Promise<void>;
  clearActiveTicket: () => Promise<void>;
};

export const useTicketStore = create<TicketState>((set, get) => ({
  hydrated: false,
  async hydrate() {
    const [activeRaw, historyRaw] = await Promise.all([
      AsyncStorage.getItem(ACTIVE_TICKET_KEY),
      AsyncStorage.getItem(HISTORY_KEY),
    ]);
    const history = historyRaw ? JSON.parse(historyRaw) as FlowTicket[] : [];
    set({
      activeTicket: activeRaw ? JSON.parse(activeRaw) as FlowTicket : undefined,
      lastTicket: history[0],
      hydrated: true,
    });
  },
  async setActiveTicket(ticket) {
    await AsyncStorage.setItem(ACTIVE_TICKET_KEY, JSON.stringify(ticket));
    set({ activeTicket: ticket });
  },
  async finishTicket(ticket) {
    const historyRaw = await AsyncStorage.getItem(HISTORY_KEY);
    const history = historyRaw ? JSON.parse(historyRaw) as FlowTicket[] : [];
    const finished = { ...ticket, status: 'finished' as const };
    await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify([finished, ...history].slice(0, 20)));
    await AsyncStorage.removeItem(ACTIVE_TICKET_KEY);
    set({ activeTicket: undefined, lastTicket: finished });
  },
  async clearActiveTicket() {
    await AsyncStorage.removeItem(ACTIVE_TICKET_KEY);
    set({ activeTicket: undefined });
  },
}));
