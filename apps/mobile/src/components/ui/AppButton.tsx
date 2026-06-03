import { Pressable, StyleSheet, Text } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { colors, radius, spacing } from '../../design/tokens';

export function AppButton({ label, icon, variant = 'primary', onPress }: { label: string; icon?: string; variant?: 'primary' | 'secondary' | 'ghost'; onPress?: () => void }) {
  const scale = useSharedValue(1);
  const animatedStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => {
        scale.value = withSpring(0.97);
      }}
      onPressOut={() => {
        scale.value = withSpring(1);
      }}
    >
      <Animated.View style={[styles.button, styles[variant], animatedStyle]}>
        {icon && <Text style={styles.icon}>{icon}</Text>}
        <Text style={[styles.label, variant === 'primary' ? styles.primaryLabel : styles.secondaryLabel]}>{label}</Text>
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 58,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  primary: { backgroundColor: colors.ink },
  secondary: { backgroundColor: colors.surfaceStrong, borderWidth: 1, borderColor: colors.line },
  ghost: { backgroundColor: 'transparent' },
  icon: { fontSize: 21 },
  label: { fontSize: 16, fontWeight: '900' },
  primaryLabel: { color: colors.softText },
  secondaryLabel: { color: colors.ink },
});
