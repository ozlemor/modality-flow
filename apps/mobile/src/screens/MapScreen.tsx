import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';
import { useEffectiveLocation } from '../hooks/useEffectiveLocation';
import { api, realtime } from '../services/api';
import { getStations } from '../services/mobility.service';
import { TRACKED_DESTINATION } from '../services/location.service';
import { Station } from '../types';

declare const require: any;

let Mapbox: any = null;
try {
  Mapbox = require('@rnmapbox/maps');
  if (process.env.EXPO_PUBLIC_MAPBOX_TOKEN) {
    Mapbox.setAccessToken(process.env.EXPO_PUBLIC_MAPBOX_TOKEN);
  }
} catch {
  Mapbox = null;
}

function stationColor(station: Station) {
  if (station.bikes_available === 0) return '#ef4444';
  if (station.bikes_available <= 2) return '#f59e0b';
  if (station.bikes_available / station.capacity > 0.65) return '#22c55e';
  return '#38bdf8';
}

function stationStatus(station: Station) {
  if (station.bikes_available === 0) return 'Vide';
  if (station.bikes_available <= 2) return 'Peu de velos';
  if (station.bikes_available / station.capacity > 0.65) return 'Tres disponible';
  return 'Disponible';
}

export function MapScreen({ onNavigate }: { onNavigate?: (tab: 'pass') => void }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Station | null>(null);
  const location = useEffectiveLocation();
  const stationsQuery = useQuery<Station[]>({
    queryKey: ['stations'],
    queryFn: getStations,
    refetchInterval: 30000,
  });
  const stations: Station[] = stationsQuery.data ?? [];
  const best = useMemo(() => [...stations].sort((a, b) => b.bikes_available - a.bikes_available)[0], [stations]);
  const activeStation = selected ?? best;
  const userPoint = location.data?.location ?? { lat: 43.6086, lon: 3.8795, label: 'Comedie - Montpellier' };

  useEffect(() => {
    realtime.connect();
    realtime.emit('stations:refresh');
    realtime.on('stations:update', (payload: Station[]) => queryClient.setQueryData(['stations'], payload));
    return () => {
      realtime.off('stations:update');
      realtime.disconnect();
    };
  }, [queryClient]);

  const routeShape = {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: [
        [userPoint.lon, userPoint.lat],
        [best?.lon ?? 3.887, best?.lat ?? 43.604],
        [TRACKED_DESTINATION.lon, TRACKED_DESTINATION.lat],
      ],
    },
    properties: {},
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Ou aller ?</Text>
          <Text style={styles.subtitle}>{location.data?.message ?? 'Ville suivie : Montpellier'}</Text>
        </View>
        <Pressable style={styles.refresh} onPress={() => stationsQuery.refetch()}>
          <Icon name="radio-outline" size={18} color="#05070a" />
          <Text style={styles.refreshText}>Live</Text>
        </Pressable>
      </View>

      <View style={styles.mapShell}>
        {Mapbox ? (
          <Mapbox.MapView style={styles.map} styleURL={Mapbox.StyleURL.Dark}>
            <Mapbox.Camera zoomLevel={13} centerCoordinate={[3.889, 43.604]} />
            <Mapbox.ShapeSource id="route" shape={routeShape}>
              <Mapbox.LineLayer id="route-line" style={{ lineColor: '#a7f3d0', lineWidth: 6, lineCap: 'round', lineJoin: 'round' }} />
            </Mapbox.ShapeSource>
            <Mapbox.PointAnnotation id="user" coordinate={[userPoint.lon, userPoint.lat]}>
              <View style={styles.userMarker}>
                <Text style={styles.userText}>Vous</Text>
              </View>
            </Mapbox.PointAnnotation>
            <Mapbox.PointAnnotation id="destination" coordinate={[TRACKED_DESTINATION.lon, TRACKED_DESTINATION.lat]}>
              <View style={styles.destinationMarker}>
                <Text style={styles.destinationText}>📍</Text>
              </View>
            </Mapbox.PointAnnotation>
            {stations.map((station) => (
              <Mapbox.PointAnnotation
                key={station.id}
                id={station.id}
                coordinate={[station.lon, station.lat]}
                onSelected={() => setSelected(station)}
              >
                <View style={[styles.marker, { backgroundColor: stationColor(station) }, best?.id === station.id && styles.markerBest]}>
                  <Text style={styles.markerText}>{station.bikes_available}</Text>
                </View>
              </Mapbox.PointAnnotation>
            ))}
          </Mapbox.MapView>
        ) : (
          <View style={styles.mapFallback}>
            <View style={styles.fakeRoute} />
            <View style={styles.fakeUser}><Text style={styles.userText}>Vous</Text></View>
            <View style={styles.fakeDestination}><Text style={styles.destinationText}>📍</Text></View>
            <Text style={styles.fallbackTitle}>Trajet Comedie → Port Marianne</Text>
            <Text style={styles.fallbackText}>Carte native indisponible. Ajoutez un token Mapbox pour afficher la carte interactive mobile.</Text>
          </View>
        )}
      </View>

      {activeStation && (
        <Card elevated>
          <View style={styles.sheetTop}>
            <View style={styles.sheetCopy}>
              <Text style={styles.label}>{best?.id === activeStation.id ? 'Station recommandee' : 'Station selectionnee'}</Text>
              <Text style={styles.stationName}>{activeStation.name}</Text>
              <Text style={styles.body}>Allez ici maintenant : {activeStation.bikes_available} velos prets.</Text>
            </View>
            <View style={[styles.statusBadge, { backgroundColor: stationColor(activeStation) }]}>
              <Text style={styles.statusText}>{stationStatus(activeStation)}</Text>
            </View>
          </View>
          <View style={styles.sheetMetrics}>
            <MiniMetric label="A pied" value="4 min" />
            <MiniMetric label="Velos" value={`${activeStation.bikes_available}/${activeStation.capacity}`} />
            <MiniMetric label="Arrivee" value="12 min" />
          </View>
          <Pressable style={styles.routeButton} onPress={() => onNavigate?.('pass')}>
            <Icon name="navigate-outline" size={18} color="#05070a" />
            <Text style={styles.routeButtonText}>Commencer avec Pass Flow</Text>
          </Pressable>
        </Card>
      )}

      <View style={styles.list}>
        {stations.map((station) => (
          <Pressable key={station.id} onPress={() => setSelected(station)}>
            <Card>
              <View style={styles.stationRow}>
                <View style={[styles.statusDot, { backgroundColor: stationColor(station) }]} />
                <View style={styles.stationText}>
                  <Text style={styles.stationNameSmall}>{station.name}</Text>
                  <Text style={styles.body}>{stationStatus(station)} · {station.bikes_available} velos disponibles</Text>
                </View>
                <Icon name="chevron-forward" color="#7f8a99" size={18} />
              </View>
            </Card>
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.miniMetric}>
      <Text style={styles.miniValue}>{value}</Text>
      <Text style={styles.miniLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#05070a' },
  content: { padding: 18, paddingBottom: 28, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  title: { color: '#f8fafc', fontSize: 30, fontWeight: '900' },
  subtitle: { color: '#8d98a8', marginTop: 4, fontSize: 13, fontWeight: '800' },
  refresh: { height: 42, borderRadius: 8, backgroundColor: '#a7f3d0', paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 6 },
  refreshText: { color: '#05070a', fontWeight: '900', fontSize: 13 },
  mapShell: { height: 430, borderRadius: 8, overflow: 'hidden', backgroundColor: '#111720', borderWidth: 1, borderColor: '#252a32' },
  map: { flex: 1 },
  mapFallback: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  fakeRoute: { position: 'absolute', width: '58%', height: 8, borderRadius: 5, backgroundColor: '#a7f3d0', transform: [{ rotate: '18deg' }] },
  fakeUser: { position: 'absolute', left: '20%', top: '38%', width: 50, height: 50, borderRadius: 25, backgroundColor: '#60a5fa', alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: '#eff6ff' },
  fakeDestination: { position: 'absolute', right: '20%', top: '50%' },
  fallbackTitle: { color: '#f8fafc', fontSize: 22, fontWeight: '900', marginTop: 150 },
  fallbackText: { color: '#aeb8c6', textAlign: 'center', lineHeight: 20, marginTop: 8 },
  userMarker: { width: 50, height: 50, borderRadius: 25, backgroundColor: '#60a5fa', borderWidth: 3, borderColor: '#eff6ff', alignItems: 'center', justifyContent: 'center' },
  userText: { color: '#03101f', fontSize: 11, fontWeight: '900' },
  destinationMarker: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center' },
  destinationText: { fontSize: 31 },
  marker: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#05070a' },
  markerBest: { borderColor: '#f8fafc', transform: [{ scale: 1.16 }] },
  markerText: { color: '#05070a', fontWeight: '900' },
  sheetTop: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  sheetCopy: { flex: 1 },
  label: { color: '#95a1b2', fontSize: 12, textTransform: 'uppercase', fontWeight: '900' },
  stationName: { color: '#f8fafc', fontSize: 25, fontWeight: '900', marginTop: 8 },
  body: { color: '#aeb8c6', fontSize: 14, marginTop: 4, lineHeight: 20 },
  statusBadge: { alignSelf: 'flex-start', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7 },
  statusText: { color: '#05070a', fontSize: 12, fontWeight: '900' },
  sheetMetrics: { flexDirection: 'row', gap: 10, marginTop: 14 },
  miniMetric: { flex: 1, borderRadius: 8, backgroundColor: '#0d131b', padding: 10 },
  miniValue: { color: '#f8fafc', fontSize: 17, fontWeight: '900' },
  miniLabel: { color: '#8d98a8', fontSize: 11, marginTop: 3 },
  routeButton: { height: 50, borderRadius: 8, backgroundColor: '#a7f3d0', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 7, marginTop: 14 },
  routeButtonText: { color: '#05070a', fontWeight: '900', fontSize: 15, textTransform: 'uppercase' },
  list: { gap: 10 },
  stationRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  stationText: { flex: 1 },
  statusDot: { width: 12, height: 12, borderRadius: 6 },
  stationNameSmall: { color: '#f8fafc', fontSize: 17, fontWeight: '800' },
});
