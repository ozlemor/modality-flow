import { StyleSheet, View } from 'react-native';

export function RoutePolyline({ points }: { points: Array<{ left: number; top: number }> }) {
  if (points.length < 2) return null;

  return (
    <>
      {points.slice(0, -1).map((point, index) => {
        const next = points[index + 1];
        const dx = next.left - point.left;
        const dy = next.top - point.top;
        const length = Math.sqrt(dx ** 2 + dy ** 2);
        const angle = Math.atan2(dy, dx) * 180 / Math.PI;
        return (
          <View
            key={`${point.left}-${point.top}-${index}`}
            style={[styles.segment, {
              left: point.left,
              top: point.top,
              width: length,
              transform: [{ rotate: `${angle}deg` }],
            }]}
          />
        );
      })}
    </>
  );
}

const styles = StyleSheet.create({
  segment: { position: 'absolute', height: 7, borderRadius: 4, backgroundColor: '#16a34a', transformOrigin: 'left center' as never },
});
