import { StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing } from '../../design/tokens';

export function BadgePill({ label, icon = '★', tone = 'green' }: { label: string; icon?: string; tone?: 'green' | 'blue' | 'orange' | 'dark' }) {
  return (
    <View style={[styles.pill, styles[tone]]}>
      <Text style={styles.icon}>{icon}</Text>
      <Text style={[styles.label, tone === 'dark' && styles.darkLabel]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    minHeight: 34,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    alignSelf: 'flex-start',
  },
  green: { backgroundColor: '#dcfce7' },
  blue: { backgroundColor: '#dbeafe' },
  orange: { backgroundColor: '#ffedd5' },
  dark: { backgroundColor: colors.ink },
  icon: { fontSize: 15 },
  label: { color: colors.ink, fontSize: 13, fontWeight: '900' },
  darkLabel: { color: colors.softText },
});
