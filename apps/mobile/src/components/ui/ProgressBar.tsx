import { DimensionValue, StyleSheet, View } from 'react-native';
import { colors, radius } from '../../design/tokens';

export function ProgressBar({ value, color = colors.greenDeep }: { value: number; color?: string }) {
  const width = `${Math.max(0, Math.min(100, value))}%` as DimensionValue;
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width, backgroundColor: color }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: { height: 11, borderRadius: radius.sm, backgroundColor: '#ebe2d4', overflow: 'hidden' },
  fill: { height: '100%', borderRadius: radius.sm },
});
