import { Pressable, StyleSheet, Text } from 'react-native';
import { Parking } from '../../types';

export function ParkingMarker({ parking, left, top, onPress }: { parking: Parking; left: number; top: number; onPress?: () => void }) {
  const ratio = parking.occupancyRatio ?? 1 - parking.available_places / Math.max(parking.capacity, 1);
  const color = ratio > 0.9 ? '#ef4444' : ratio > 0.72 ? '#f59e0b' : '#60a5fa';

  return (
    <Pressable onPress={onPress} style={[styles.marker, { left, top, backgroundColor: color }]}>
      <Text style={styles.text}>P</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  marker: { position: 'absolute', width: 34, height: 34, marginLeft: -17, marginTop: -17, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#ffffff' },
  text: { color: '#07130d', fontSize: 15, fontWeight: '900' },
});
