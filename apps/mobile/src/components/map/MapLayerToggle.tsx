import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

export type MapLayer = 'recommended' | 'all' | 'bikes' | 'parkings' | 'bus' | 'tram' | 'traffic';

const labels: Record<Exclude<MapLayer, 'recommended'>, string> = {
  all: 'Tout',
  bikes: 'Velos',
  parkings: 'Parkings',
  bus: 'Bus',
  tram: 'Tram',
  traffic: 'Trafic',
};

export function MapLayerToggle({ active, onChange }: { active: MapLayer; onChange: (layer: MapLayer) => void }) {
  const layers = Object.keys(labels) as Array<Exclude<MapLayer, 'recommended'>>;

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
      {layers.map((layer) => (
        <Pressable key={layer} onPress={() => onChange(active === layer ? 'recommended' : layer)} style={[styles.chip, active === layer && styles.active]}>
          <Text style={[styles.text, active === layer && styles.activeText]}>{labels[layer]}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: { gap: 8, paddingRight: 8 },
  chip: { height: 38, borderRadius: 12, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#e5e7eb' },
  active: { backgroundColor: '#10201a', borderColor: '#10201a' },
  text: { color: '#10201a', fontSize: 13, fontWeight: '900' },
  activeText: { color: '#f8fbf7' },
});
