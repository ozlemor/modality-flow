import { StyleSheet, Text, View } from 'react-native';
import { FlowTicket } from '../../features/ticket/ticket.types';

export function PassCard({ ticket }: { ticket?: FlowTicket }) {
  return (
    <View style={styles.card}>
      <View style={styles.top}>
        <View>
          <Text style={styles.brand}>Pass Flow</Text>
          <Text style={styles.subtitle}>Votre pass mobilite intelligent</Text>
        </View>
        <Text style={styles.status}>{ticket ? 'ACTIF' : 'PRET'}</Text>
      </View>
      <Text style={styles.mode}>{ticket ? ticket.mode.toUpperCase() : 'MULTIMODAL'}</Text>
      <View style={styles.qrBox}>
        <Text style={styles.qrText}>{ticket?.qr_data ? ticket.qr_data : 'QR indisponible pour ce trajet'}</Text>
      </View>
      {ticket && <Text style={styles.ticketId}>Ticket #{ticket.ticket_id.slice(0, 8)}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 24, backgroundColor: '#111827', padding: 20, minHeight: 250, borderWidth: 1, borderColor: '#2d3748', justifyContent: 'space-between' },
  top: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  brand: { color: '#f8fafc', fontSize: 28, fontWeight: '900' },
  subtitle: { color: '#9ca3af', fontSize: 13, marginTop: 3, fontWeight: '800' },
  status: { color: '#10201a', backgroundColor: '#a7f3d0', overflow: 'hidden', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, fontSize: 11, fontWeight: '900', alignSelf: 'flex-start' },
  mode: { color: '#a7f3d0', fontSize: 34, fontWeight: '900', letterSpacing: 0 },
  qrBox: { minHeight: 58, borderRadius: 8, backgroundColor: '#f8fafc', padding: 12, justifyContent: 'center' },
  qrText: { color: '#111827', fontSize: 12, fontWeight: '800' },
  ticketId: { color: '#cbd5e1', fontSize: 13, fontWeight: '900' },
});
