import { StyleSheet, Text, View } from 'react-native';

export function ScoreRing({ score, label = 'Score' }: { score: number; label?: string }) {
  const safeScore = Math.max(0, Math.min(100, Math.round(score)));

  return (
    <View style={styles.ring}>
      <View style={[styles.arc, { opacity: 0.25 + safeScore / 140 }]} />
      <Text style={styles.score}>{safeScore}</Text>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  ring: { width: 82, height: 82, borderRadius: 41, borderWidth: 8, borderColor: '#a7f3d0', alignItems: 'center', justifyContent: 'center', backgroundColor: '#0d1913' },
  arc: { position: 'absolute', width: 82, height: 82, borderRadius: 41, backgroundColor: '#a7f3d0' },
  score: { color: '#f8fafc', fontSize: 22, fontWeight: '900' },
  label: { color: '#cbd5e1', fontSize: 10, fontWeight: '800' },
});
