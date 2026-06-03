import { StyleSheet, Text, View } from 'react-native';
import { TicketSegment } from '../../features/ticket/ticket.types';

export function TicketTimeline({ segments }: { segments: TicketSegment[] }) {
  return (
    <View style={styles.timeline}>
      {segments.map((segment, index) => (
        <View key={`${segment.startedAt}-${index}`} style={styles.row}>
          <View style={styles.dot} />
          <View style={styles.copy}>
            <Text style={styles.title}>{segment.label}</Text>
            <Text style={styles.meta}>{new Date(segment.startedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  timeline: { gap: 10 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#a7f3d0' },
  copy: { flex: 1 },
  title: { color: '#f8fafc', fontSize: 15, fontWeight: '900' },
  meta: { color: '#8d98a8', fontSize: 12, marginTop: 2, fontWeight: '800' },
});
