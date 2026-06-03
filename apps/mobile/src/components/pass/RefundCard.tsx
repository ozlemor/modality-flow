import { Pressable, StyleSheet, Text, View } from 'react-native';

export function RefundCard({ amount, recovered, onRecover }: { amount?: number; recovered?: boolean; onRecover?: () => void }) {
  if (!amount || amount <= 0) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Remboursement disponible</Text>
      <Text style={styles.amount}>{amount.toFixed(2)} €</Text>
      <Pressable style={styles.button} onPress={onRecover} disabled={recovered}>
        <Text style={styles.buttonText}>{recovered ? 'Remboursement recupere' : 'Recuperer mon remboursement'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 8, backgroundColor: '#ecfdf5', padding: 16, gap: 8 },
  title: { color: '#10201a', fontSize: 14, fontWeight: '900' },
  amount: { color: '#137a4b', fontSize: 28, fontWeight: '900' },
  button: { minHeight: 48, borderRadius: 8, backgroundColor: '#10201a', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  buttonText: { color: '#f8fbf7', fontWeight: '900', fontSize: 14 },
});
