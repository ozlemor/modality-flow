import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, radius, shadows, spacing } from '../../design/tokens';

export function AppCard({ children, tone = 'light', padded = true }: { children: ReactNode; tone?: 'light' | 'dark' | 'green' | 'blue'; padded?: boolean }) {
  return <View style={[styles.card, styles[tone], padded && styles.padded]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: 'hidden',
    ...shadows.card,
  },
  padded: { padding: spacing.lg },
  light: { backgroundColor: colors.surfaceStrong, borderColor: colors.line },
  dark: { backgroundColor: colors.night, borderColor: '#26372d' },
  green: { backgroundColor: '#dcfce7', borderColor: '#bbf7d0' },
  blue: { backgroundColor: '#dbeafe', borderColor: '#bfdbfe' },
});
