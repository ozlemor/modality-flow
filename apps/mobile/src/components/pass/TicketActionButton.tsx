import { Pressable, StyleSheet, Text } from 'react-native';

export function TicketActionButton({ label, icon, tone = 'primary', onPress }: { label: string; icon: string; tone?: 'primary' | 'secondary' | 'danger'; onPress?: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.button, styles[tone]]}>
      <Text style={styles.icon}>{icon}</Text>
      <Text style={[styles.label, tone === 'primary' ? styles.primaryLabel : styles.secondaryLabel]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { minHeight: 56, borderRadius: 8, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  primary: { backgroundColor: '#a7f3d0' },
  secondary: { backgroundColor: '#182231', borderWidth: 1, borderColor: '#2d3748' },
  danger: { backgroundColor: '#fee2e2' },
  icon: { fontSize: 20 },
  label: { fontSize: 15, fontWeight: '900' },
  primaryLabel: { color: '#05070a' },
  secondaryLabel: { color: '#f8fafc' },
});
