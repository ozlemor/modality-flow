import { StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing, typography } from '../../design/tokens';

export function StatCard({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <View style={styles.card}>
      <Text style={styles.icon}>{icon}</Text>
      <Text style={styles.value}>{value}</Text>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    minHeight: 104,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceStrong,
    borderWidth: 1,
    borderColor: colors.line,
    padding: spacing.md,
  },
  icon: { fontSize: 22 },
  value: { color: colors.ink, fontSize: typography.subtitle, fontWeight: '900', marginTop: spacing.sm },
  label: { color: colors.muted, fontSize: typography.small, marginTop: 3, fontWeight: '700' },
});
