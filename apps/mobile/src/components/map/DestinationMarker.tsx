import { StyleSheet, Text, View } from 'react-native';

export function DestinationMarker({ left, top }: { left: number; top: number }) {
  return (
    <View style={[styles.marker, { left, top }]}>
      <Text style={styles.text}>📍</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  marker: { position: 'absolute', width: 42, height: 42, marginLeft: -21, marginTop: -36, alignItems: 'center', justifyContent: 'center' },
  text: { fontSize: 34 },
});
