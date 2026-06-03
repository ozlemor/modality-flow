import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

export function BottomSheet({ children }: { children: ReactNode }) {
  return (
    <View style={styles.sheet}>
      <View style={styles.handle} />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24, borderRadius: 8, backgroundColor: '#0b1118', borderWidth: 1, borderColor: '#263142', padding: 14, gap: 12 },
  handle: { alignSelf: 'center', width: 46, height: 5, borderRadius: 3, backgroundColor: '#334155', marginBottom: 2 },
});
