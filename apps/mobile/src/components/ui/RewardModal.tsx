import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInDown, ZoomIn } from 'react-native-reanimated';
import { ProgressBar } from './ProgressBar';

export function RewardModal({
  visible,
  xp,
  co2SavedKg,
  badgeProgress,
  onClose,
}: {
  visible: boolean;
  xp: number;
  co2SavedKg: number;
  badgeProgress: number;
  onClose: () => void;
}) {
  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <Animated.View entering={ZoomIn.duration(260)} style={styles.card}>
          <Text style={styles.confetti}>🎉</Text>
          <Text style={styles.title}>Bravo</Text>
          <Text style={styles.subtitle}>Pass termine</Text>
          <Animated.Text entering={FadeInDown.delay(120)} style={styles.xp}>+{xp} XP</Animated.Text>
          <Text style={styles.body}>{co2SavedKg.toFixed(1)} kg de CO2 economises</Text>
          <View style={styles.progressBox}>
            <Text style={styles.progressLabel}>Badge en progression</Text>
            <ProgressBar value={badgeProgress} color="#a7f3d0" />
          </View>
          <Pressable style={styles.button} onPress={onClose}>
            <Text style={styles.buttonText}>Continuer</Text>
          </Pressable>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.72)', alignItems: 'center', justifyContent: 'center', padding: 22 },
  card: { width: '100%', maxWidth: 420, borderRadius: 24, backgroundColor: '#fffaf0', padding: 24, alignItems: 'center' },
  confetti: { fontSize: 52 },
  title: { color: '#10201a', fontSize: 34, fontWeight: '900', marginTop: 6 },
  subtitle: { color: '#63736c', fontSize: 16, fontWeight: '800', marginTop: 4 },
  xp: { color: '#137a4b', fontSize: 42, fontWeight: '900', marginTop: 18 },
  body: { color: '#10201a', fontSize: 18, fontWeight: '800', marginTop: 6 },
  progressBox: { width: '100%', marginTop: 20, gap: 8 },
  progressLabel: { color: '#10201a', fontSize: 14, fontWeight: '900' },
  button: { width: '100%', height: 54, borderRadius: 14, backgroundColor: '#10201a', alignItems: 'center', justifyContent: 'center', marginTop: 22 },
  buttonText: { color: '#f8fbf7', fontSize: 16, fontWeight: '900' },
});
