import { Text, TouchableOpacity, StyleSheet } from 'react-native';

export function PrimaryButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <TouchableOpacity onPress={onPress} style={styles.button} activeOpacity={0.8}>
      <Text style={styles.text}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    borderRadius: 16,
    backgroundColor: '#34d399',
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  text: {
    textAlign: 'center',
    fontSize: 18,
    fontWeight: 'bold',
    color: '#09090b',
  },
});
