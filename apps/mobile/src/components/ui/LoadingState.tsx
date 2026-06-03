import { StyleSheet, Text, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';
import { useEffect } from 'react';
import { colors, radius, spacing, typography } from '../../design/tokens';

export function LoadingState({ label = 'On prepare ta recommandation...' }: { label?: string }) {
  const opacity = useSharedValue(0.45);
  useEffect(() => {
    opacity.value = withRepeat(withTiming(1, { duration: 850 }), -1, true);
  }, [opacity]);
  const animated = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <View style={styles.wrap}>
      <Animated.View style={[styles.skeleton, animated]} />
      <Animated.View style={[styles.skeletonSmall, animated]} />
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md },
  skeleton: { height: 148, borderRadius: radius.lg, backgroundColor: '#eadfce' },
  skeletonSmall: { height: 64, borderRadius: radius.md, backgroundColor: '#eadfce' },
  label: { color: colors.muted, fontSize: typography.body, fontWeight: '800', textAlign: 'center' },
});
