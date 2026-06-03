import { StyleSheet, Text, View } from 'react-native';

export function UserMarker({ left, top }: { left: number; top: number }) {
  return (
    <View style={[styles.marker, { left, top }]}>
      <Text style={styles.text}>Vous</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  marker: { position: 'absolute', width: 54, height: 54, marginLeft: -27, marginTop: -27, borderRadius: 27, backgroundColor: '#2563eb', alignItems: 'center', justifyContent: 'center', borderWidth: 4, borderColor: '#dbeafe' },
  text: { color: '#ffffff', fontSize: 11, fontWeight: '900' },
});
