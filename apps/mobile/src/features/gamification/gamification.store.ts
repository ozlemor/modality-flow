import { create } from 'zustand';
import { TicketMode } from '../ticket/ticket.types';

type Reward = {
  xp: number;
  co2SavedKg: number;
  title: string;
  badgeProgress: number;
};

type GamificationState = {
  xp: number;
  streak: number;
  co2SavedKg: number;
  lastReward?: Reward;
  addTripReward: (input: { mode: TicketMode; multimodal: boolean; co2SavedKg: number }) => Reward;
  dismissReward: () => void;
};

const modeXp: Record<TicketMode, number> = {
  velo: 40,
  marche: 30,
  tram: 25,
  bus: 25,
  voiture: 0,
};

export const useGamificationStore = create<GamificationState>((set, get) => ({
  xp: 1640,
  streak: 4,
  co2SavedKg: 18.4,
  addTripReward({ mode, multimodal, co2SavedKg }) {
    const xp = modeXp[mode] + 20 + 15 + 10 + (multimodal ? 20 : 0);
    const reward = {
      xp,
      co2SavedKg,
      title: 'Pass termine',
      badgeProgress: Math.min(100, 80 + Math.round(xp / 10)),
    };
    set({
      xp: get().xp + xp,
      co2SavedKg: get().co2SavedKg + co2SavedKg,
      lastReward: reward,
    });
    return reward;
  },
  dismissReward() {
    set({ lastReward: undefined });
  },
}));
