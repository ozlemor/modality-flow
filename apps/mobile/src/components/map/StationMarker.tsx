import { Pressable, StyleSheet, Text } from 'react-native';
import { Station } from '../../types';

export function stationColor(station: Station) {
  if (station.bikes_available <= 0) return '#ef4444';
  if (station.bikes_available <= 2) return '#f59e0b';
  if (station.bikes_available / Math.max(station.capacity, 1) > 0.55) return '#22c55e';
  return '#38bdf8';
}

export function StationMarker({ station, left, top, recommended, onPress }: { station: Station; left: number; top: number; recommended?: boolean; onPress?: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.marker, { left, top, backgroundColor: stationColor(station) }, recommended && styles.recommended]}>
      <Text style={styles.text}>{station.bikes_available}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  marker: { position: 'absolute', width: 42, height: 42, marginLeft: -21, marginTop: -21, borderRadius: 21, alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: '#ffffff' },
  recommended: { width: 52, height: 52, marginLeft: -26, marginTop: -26, borderRadius: 26, borderColor: '#10201a', borderWidth: 4 },
  text: { color: '#07130d', fontSize: 14, fontWeight: '900' },
});
