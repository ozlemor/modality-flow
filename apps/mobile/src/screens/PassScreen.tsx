import { useEffect, useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { PassCard } from '../components/pass/PassCard';
import { RefundCard } from '../components/pass/RefundCard';
import { TicketActionButton } from '../components/pass/TicketActionButton';
import { TicketTimeline } from '../components/pass/TicketTimeline';
import { RewardModal } from '../components/ui/RewardModal';
import { useGamificationStore } from '../features/gamification/gamification.store';
import { FlowTicket, TicketMode } from '../features/ticket/ticket.types';
import { useTicketStore } from '../features/ticket/ticket.store';
import { useEffectiveLocation } from '../hooks/useEffectiveLocation';
import {
  calculateDistanceKm,
  TRACKED_CITY_DESTINATION,
  TRACKED_CITY_ORIGIN,
  MobilityPoint,
} from '../services/location.service';
import { addSegment, alightTicket, boardTicket, getOrCreateDeviceToken, recoverRefund } from '../services/ticket.service';

const modeLabels: Record<TicketMode, string> = {
  velo: 'Velo',
  tram: 'Tram',
  bus: 'Bus',
  marche: 'Marche',
  voiture: 'Voiture',
};

export function PassScreen() {
  const location = useEffectiveLocation();
  const ticketStore = useTicketStore();
  const gamification = useGamificationStore();
  const [loadingAction, setLoadingAction] = useState<string>();
  const activeTicket = ticketStore.activeTicket;

  useEffect(() => {
    if (!ticketStore.hydrated) ticketStore.hydrate();
  }, [ticketStore]);

  const currentPoint = location.data?.location ?? TRACKED_CITY_ORIGIN;
  const lastTicket = ticketStore.lastTicket;

  async function startPass(mode: TicketMode, stationId?: string) {
    setLoadingAction(`start-${mode}`);
    try {
      const deviceToken = await getOrCreateDeviceToken();
      const payload = {
        device_token: deviceToken,
        mode,
        station_id: stationId,
        terminal_id: 'mobile-app',
        lat: currentPoint.lat,
        lon: currentPoint.lon,
      };
      const response = await boardTicket(payload);
      const ticket: FlowTicket = {
        ticket_id: String(response?.ticket_id ?? response?.id ?? `local-${Date.now()}`),
        status: 'active',
        mode,
        startTime: new Date().toISOString(),
        startLocation: currentPoint,
        qr_data: response?.qr_data,
        segments: [{ mode, startedAt: new Date().toISOString(), stationId, label: modeLabels[mode] }],
        raw: response,
      };
      await ticketStore.setActiveTicket(ticket);
    } catch (error) {
      Alert.alert('Pass indisponible', 'Le service Pass ne repond pas pour le moment.');
    } finally {
      setLoadingAction(undefined);
    }
  }

  async function addTransport(mode: TicketMode) {
    if (!activeTicket) return;
    setLoadingAction(`segment-${mode}`);
    try {
      const deviceToken = await getOrCreateDeviceToken();
      await addSegment({
        ticket_id: activeTicket.ticket_id,
        device_token: deviceToken,
        mode,
        terminal_id: 'mobile-app',
        lat: currentPoint.lat,
        lon: currentPoint.lon,
      });
      await ticketStore.setActiveTicket({
        ...activeTicket,
        segments: [...activeTicket.segments, { mode, startedAt: new Date().toISOString(), label: modeLabels[mode] }],
      });
    } finally {
      setLoadingAction(undefined);
    }
  }

  async function finishPass() {
    if (!activeTicket) return;
    setLoadingAction('finish');
    try {
      const deviceToken = await getOrCreateDeviceToken();
      const endLocation: MobilityPoint = location.data?.usesTrackedCityLocation ? TRACKED_CITY_DESTINATION : currentPoint;
      const distance = calculateDistanceKm(activeTicket.startLocation, endLocation);
      const response = await alightTicket({
        ticket_id: activeTicket.ticket_id,
        device_token: deviceToken,
        terminal_id: 'mobile-app',
        lat: endLocation.lat,
        lon: endLocation.lon,
        distance_reelle_km: Number(distance.toFixed(2)),
      });
      const co2SavedKg = Math.max(0.4, Number((distance * 0.12).toFixed(1)));
      const reward = gamification.addTripReward({
        mode: activeTicket.mode,
        multimodal: activeTicket.segments.length > 1,
        co2SavedKg,
      });
      await ticketStore.finishTicket({
        ...activeTicket,
        status: 'finished',
        endTime: new Date().toISOString(),
        endLocation,
        pricePaid: Number(response?.prix_paye ?? response?.price_paid ?? response?.price ?? 1.7),
        refundAvailable: Number(response?.remboursement ?? response?.refund_available ?? 0),
        co2SavedKg,
        xpEarned: reward.xp,
        raw: response,
      });
    } catch {
      Alert.alert('Fin de trajet impossible', 'On garde votre Pass actif. Reessayez dans un instant.');
    } finally {
      setLoadingAction(undefined);
    }
  }

  async function recover(ticket: FlowTicket) {
    setLoadingAction('refund');
    try {
      await recoverRefund(ticket.ticket_id, 'mobile-app');
      await ticketStore.finishTicket({ ...ticket, refundRecovered: true });
    } finally {
      setLoadingAction(undefined);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.title}>Pass</Text>
        <Text style={styles.subtitle}>Un seul pass pour votre trajet multimodal.</Text>
      </View>

      <PassCard ticket={activeTicket} />

      {!activeTicket ? (
        <View style={styles.actions}>
          <TicketActionButton label={loadingAction === 'start-velo' ? 'Demarrage...' : 'Demarrer velo'} icon="🚲" onPress={() => startPass('velo')} />
          <TicketActionButton label="Demarrer tram" icon="🚋" tone="secondary" onPress={() => startPass('tram')} />
          <TicketActionButton label="Demarrer bus" icon="🚌" tone="secondary" onPress={() => startPass('bus')} />
        </View>
      ) : (
        <View style={styles.activeArea}>
          <View style={styles.statusCard}>
            <Text style={styles.statusTitle}>Pass Flow en cours</Text>
            <Text style={styles.statusText}>Depart {new Date(activeTicket.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {modeLabels[activeTicket.mode]}</Text>
          </View>

          <Text style={styles.sectionTitle}>Timeline</Text>
          <TicketTimeline segments={activeTicket.segments} />

          <Text style={styles.sectionTitle}>Ajouter un transport</Text>
          <View style={styles.segmentRow}>
            <TicketActionButton label="Velo" icon="🚲" tone="secondary" onPress={() => addTransport('velo')} />
            <TicketActionButton label="Tram" icon="🚋" tone="secondary" onPress={() => addTransport('tram')} />
            <TicketActionButton label="Bus" icon="🚌" tone="secondary" onPress={() => addTransport('bus')} />
          </View>

          <TicketActionButton label={loadingAction === 'finish' ? 'Fin en cours...' : 'Terminer mon trajet'} icon="✅" onPress={finishPass} />
        </View>
      )}

      {lastTicket && !activeTicket && (
        <View style={styles.resultCard}>
          <Text style={styles.sectionTitle}>Dernier trajet</Text>
          <Text style={styles.resultText}>Prix paye : {(lastTicket.pricePaid ?? 0).toFixed(2)} €</Text>
          <Text style={styles.resultText}>XP gagnes : {lastTicket.xpEarned ?? 0}</Text>
          <Text style={styles.resultText}>CO2 economise : {(lastTicket.co2SavedKg ?? 0).toFixed(1)} kg</Text>
          <RefundCard amount={lastTicket.refundAvailable} recovered={lastTicket.refundRecovered} onRecover={() => recover(lastTicket)} />
        </View>
      )}

      <RewardModal
        visible={Boolean(gamification.lastReward)}
        xp={gamification.lastReward?.xp ?? 0}
        co2SavedKg={gamification.lastReward?.co2SavedKg ?? 0}
        badgeProgress={gamification.lastReward?.badgeProgress ?? 0}
        onClose={gamification.dismissReward}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#05070a' },
  content: { padding: 18, paddingBottom: 28, gap: 14, maxWidth: 900, width: '100%', alignSelf: 'center' },
  header: { gap: 4 },
  title: { color: '#f8fafc', fontSize: 30, fontWeight: '900' },
  subtitle: { color: '#9ca3af', fontSize: 14, fontWeight: '800' },
  actions: { gap: 10 },
  activeArea: { gap: 12 },
  statusCard: { borderRadius: 8, backgroundColor: '#102017', borderWidth: 1, borderColor: '#286243', padding: 14 },
  statusTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '900' },
  statusText: { color: '#a7f3d0', fontSize: 14, marginTop: 4, fontWeight: '800' },
  sectionTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '900', marginTop: 4 },
  segmentRow: { gap: 8 },
  resultCard: { borderRadius: 8, backgroundColor: '#111720', borderWidth: 1, borderColor: '#263142', padding: 16, gap: 8 },
  resultText: { color: '#d1d5db', fontSize: 15, fontWeight: '800' },
});
