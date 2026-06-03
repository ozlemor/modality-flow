import { Pressable, StyleSheet, Text } from 'react-native';
import { TamStop } from '../../types';

export function TamStopMarker({ stop, left, top, onPress }: { stop: TamStop; left: number; top: number; onPress?: () => void }) {
  const mode = stop.mode?.toLowerCase().includes('tram') ? 'T' : 'B';

  return (
    <Pressable onPress={onPress} style={[styles.marker, { left, top }]}>
      <Text style={styles.text}>{mode}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  marker: { position: 'absolute', width: 30, height: 30, marginLeft: -15, marginTop: -15, borderRadius: 15, backgroundColor: '#7c3aed', alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#ffffff' },
  text: { color: '#ffffff', fontSize: 13, fontWeight: '900' },
});
