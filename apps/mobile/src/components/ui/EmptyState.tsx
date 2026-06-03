import { StyleSheet, Text, View } from 'react-native';
import { colors, spacing, typography } from '../../design/tokens';
import { AppCard } from './AppCard';

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <AppCard>
      <View style={styles.wrap}>
        <Text style={styles.icon}>✨</Text>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.body}>{body}</Text>
      </View>
    </AppCard>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', gap: spacing.sm },
  icon: { fontSize: 34 },
  title: { color: colors.ink, fontSize: typography.subtitle, fontWeight: '900', textAlign: 'center' },
  body: { color: colors.muted, fontSize: typography.body, lineHeight: 23, textAlign: 'center' },
});
