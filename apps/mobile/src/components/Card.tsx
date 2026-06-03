import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

export function Card({ children, elevated = false }: { children: ReactNode; elevated?: boolean }) {
  return <View style={[styles.card, elevated && styles.elevated]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 8,
    backgroundColor: '#15171c',
    padding: 18,
    borderWidth: 1,
    borderColor: '#252a32',
  },
  elevated: {
    backgroundColor: '#1b1f27',
    borderColor: '#343b47',
  },
});
