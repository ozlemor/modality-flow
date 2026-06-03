import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import { DestinationMarker } from '../components/map/DestinationMarker';
import { MapLayer, MapLayerToggle } from '../components/map/MapLayerToggle';
import { ParkingMarker } from '../components/map/ParkingMarker';
import { projectPoint, RealRasterMap } from '../components/map/RealRasterMap';
import { RoutePolyline } from '../components/map/RoutePolyline';
import { StationMarker, stationColor } from '../components/map/StationMarker';
import { TamStopMarker } from '../components/map/TamStopMarker';
import { UserMarker } from '../components/map/UserMarker';
import { TicketActionButton } from '../components/pass/TicketActionButton';
import { BottomSheet } from '../components/ui/BottomSheet';
import { LiveChip } from '../components/ui/LiveChip';
import { ScoreRing } from '../components/ui/ScoreRing';
import { buildLocalRecommendation, LocalMode } from '../features/recommendation/recommendation.logic';
import { useTicketStore } from '../features/ticket/ticket.store';
import { FlowTicket, TicketMode } from '../features/ticket/ticket.types';
import { useEffectiveLocation } from '../hooks/useEffectiveLocation';
import { useTimeContext } from '../hooks/useTimeContext';
import { calculateDistanceKm, TRACKED_CITY_DESTINATION, TRACKED_CITY_ORIGIN } from '../services/location.service';
import {
  calculateJourney,
  getAqi,
  getParkings,
  getStations,
  getTamRoutes,
  getTamStops,
  getWeather,
  predictStation,
} from '../services/mobility.service';
import { boardTicket, getOrCreateDeviceToken } from '../services/ticket.service';
import { JourneyOption, JourneyResponse, Parking, Station, TamRoute, TamStop } from '../types';

type SheetTab = 'summary' | 'options' | 'stations' | 'transport' | 'pass';
type PositionedStation = Station & { distanceKm: number };
type PositionedParking = Parking & { distanceKm: number };
type PositionedStop = TamStop & { id: string; lat: number; lon: number; mode: string; distanceKm: number };
type StationCluster = {
  key: string;
  count: number;
  bikes: number;
  left: number;
  top: number;
  station?: PositionedStation;
};

const MAP_WIDTH = 900;
const MAP_HEIGHT = 560;
const MAP_ZOOM = 14;
const MAX_CONTEXT_MARKERS = 30;
const MAX_TAM_MARKERS = 22;

const modeIcons: Record<string, string> = {
  bike: '🚲',
  walk: '🚶',
  transit: '🚋',
  tram: '🚋',
  bus: '🚌',
  car: '🚗',
};

export function MapScreen({ onNavigate }: { onNavigate?: (tab: 'pass') => void }) {
  const [layer, setLayer] = useState<MapLayer>('recommended');
  const [tab, setTab] = useState<SheetTab>('summary');
  const [selectedStation, setSelectedStation] = useState<Station | null>(null);
  const [selectedStop, setSelectedStop] = useState<TamStop | null>(null);
  const [stationPrediction, setStationPrediction] = useState<number | null>(null);
  const [startingPass, setStartingPass] = useState(false);
  const timeContext = useTimeContext();
  const location = useEffectiveLocation();
  const ticketStore = useTicketStore();

  const stationsQuery = useQuery({ queryKey: ['stations'], queryFn: getStations, refetchInterval: 20000 });
  const parkingsQuery = useQuery({ queryKey: ['parkings'], queryFn: getParkings, refetchInterval: 60000 });
  const stopsQuery = useQuery({ queryKey: ['tam-stops'], queryFn: getTamStops, refetchInterval: 60000 });
  const routesQuery = useQuery({ queryKey: ['tam-routes'], queryFn: getTamRoutes, refetchInterval: 60000 });
  const weatherQuery = useQuery({ queryKey: ['weather'], queryFn: getWeather, refetchInterval: 60000 });
  const aqiQuery = useQuery({ queryKey: ['aqi'], queryFn: getAqi, refetchInterval: 60000 });

  const stations: Station[] = stationsQuery.data ?? [];
  const parkings: Parking[] = parkingsQuery.data ?? [];
  const allStops = normalizeStops(stopsQuery.data ?? []);
  const routes: TamRoute[] = routesQuery.data ?? [];
  const weather = weatherQuery.data;
  const aqi = aqiQuery.data?.indice_qualite ?? aqiQuery.data?.aqi ?? 3;
  const userPoint = location.data?.location ?? TRACKED_CITY_ORIGIN;
  const center = { lat: 43.605, lon: 3.889 };
  const stationsByDistance = useMemo<PositionedStation[]>(() => stations
    .map((station: Station) => ({ ...station, distanceKm: calculateDistanceKm(station, userPoint) }))
    .sort((a: PositionedStation, b: PositionedStation) => a.distanceKm - b.distanceKm), [stations, userPoint.lat, userPoint.lon]);
  const parkingsByDistance = useMemo<PositionedParking[]>(() => parkings
    .map((parking: Parking) => ({ ...parking, distanceKm: calculateDistanceKm(parking, userPoint) }))
    .sort((a: PositionedParking, b: PositionedParking) => a.distanceKm - b.distanceKm), [parkings, userPoint.lat, userPoint.lon]);
  const stops = useMemo(() => allStops
    .map((stop) => ({ ...stop, distanceKm: calculateDistanceKm(stop, userPoint) }))
    .sort((a, b) => a.distanceKm - b.distanceKm), [allStops, userPoint.lat, userPoint.lon]);
  const bestStation = useMemo(() => [...stations].sort((a, b) => b.bikes_available - a.bikes_available)[0], [stations]);
  const activeStation = selectedStation ?? bestStation;
  const visibleStations = useMemo(() => getVisiblePoints(stationsByDistance, center, MAX_CONTEXT_MARKERS), [stationsByDistance, center.lat, center.lon]);
  const visibleParkings = useMemo(() => getVisiblePoints(parkingsByDistance, center, layer === 'all' ? 10 : MAX_CONTEXT_MARKERS), [parkingsByDistance, center.lat, center.lon, layer]);
  const visibleStops = useMemo(() => getVisibleTamStops(stops, center, userPoint, layer), [stops, center.lat, center.lon, userPoint.lat, userPoint.lon, layer]);
  const stationClusters = useMemo(() => clusterStations(
    visibleStations.filter((station) => station.id !== activeStation?.id),
    center,
  ), [visibleStations, activeStation?.id, center.lat, center.lon]);
  const traffic = getTrafficSignal(timeContext.currentHour);
  const localRecommendation = buildLocalRecommendation({
    environment: {
      hour: timeContext.currentHour,
      label: timeContext.periodLabel,
      temperature: weather?.temperature ?? 20,
      precipitation: weather?.precipitation ?? 0,
      windSpeed: weather?.windSpeed ?? weather?.wind_speed ?? 10,
      aqi,
      trafficIndex: traffic.index,
      bikeComfort: 'good',
      recommendationReason: '',
      updatedAt: new Date().toISOString(),
    },
    timeContext,
    stations,
  });

  const journey = useMutation<JourneyResponse>({
    mutationFn: async () => calculateJourney({
      lat_a: userPoint.lat,
      lon_a: userPoint.lon,
      lat_b: TRACKED_CITY_DESTINATION.lat,
      lon_b: TRACKED_CITY_DESTINATION.lon,
      heure: timeContext.currentHour,
      precipitation: weather?.precipitation ?? 0,
      temperature: weather?.temperature ?? 20,
      wind_speed: weather?.windSpeed ?? weather?.wind_speed ?? 10,
      indice_qualite: aqi,
    }),
  });

  useEffect(() => {
    if (!ticketStore.hydrated) ticketStore.hydrate();
  }, [ticketStore]);

  useEffect(() => {
    if (userPoint.lat && weather && stations.length && !journey.data && !journey.isPending) {
      journey.mutate();
    }
  }, [userPoint.lat, weather, stations.length]);

  useEffect(() => {
    async function loadPrediction() {
      if (!activeStation) return;
      try {
        const prediction = await predictStation(activeStation.id);
        setStationPrediction(Number(prediction?.predicted_bikes_30min ?? prediction?.prediction ?? activeStation.bikes_available));
      } catch {
        setStationPrediction(null);
      }
    }
    loadPrediction();
  }, [activeStation?.id]);

  const userPosition = projectPoint(userPoint, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT);
  const destinationPosition = projectPoint(TRACKED_CITY_DESTINATION, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT);
  const stationPosition = activeStation ? projectPoint(activeStation, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT) : undefined;
  const routePoints = stationPosition ? [userPosition, stationPosition, destinationPosition] : [userPosition, destinationPosition];
  const options = buildOptions(journey.data?.options, localRecommendation.options, timeContext.now);
  const recommended = journey.data?.recommended;
  const showBikes = layer === 'all' || layer === 'bikes';
  const showParkings = layer === 'all' || layer === 'parkings';
  const showBus = layer === 'bus';
  const showTram = layer === 'tram';
  const showTransit = showBus || showTram;
  const showTraffic = layer === 'all' || layer === 'traffic';

  async function startPass(mode: TicketMode = 'velo') {
    setStartingPass(true);
    try {
      const deviceToken = await getOrCreateDeviceToken();
      const response = await boardTicket({
        device_token: deviceToken,
        mode,
        station_id: activeStation?.id,
        terminal_id: 'mobile-app',
        lat: userPoint.lat,
        lon: userPoint.lon,
      });
      const ticket: FlowTicket = {
        ticket_id: String(response?.ticket_id ?? response?.id ?? `local-${Date.now()}`),
        status: 'active',
        mode,
        startTime: new Date().toISOString(),
        startLocation: userPoint,
        qr_data: response?.qr_data,
        segments: [{ mode, stationId: activeStation?.id, label: mode === 'velo' ? 'Velo' : mode, startedAt: new Date().toISOString() }],
        raw: response,
      };
      await ticketStore.setActiveTicket(ticket);
      onNavigate?.('pass');
    } catch {
      Alert.alert('Pass indisponible', 'Impossible de demarrer le Pass pour le moment.');
    } finally {
      setStartingPass(false);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.headerFloating}>
        <View style={styles.headerCopy}>
          <Text style={styles.time}>{timeContext.time} · {timeContext.periodLabel}</Text>
          <Text style={styles.context}>{weatherLabel(weather?.temperature, weather?.precipitation)} · {airLabel(aqi)} · {traffic.label}</Text>
          {location.data?.isOutsideMontpellier && <Text style={styles.trackedCity}>Vous etes hors Montpellier · ville suivie : Montpellier</Text>}
        </View>
        <LiveChip label="LIVE" />
      </View>

      {location.data?.isOutsideMontpellier && location.data.montpellierDistance && (
        <View style={styles.accessCard}>
          <Text style={styles.accessTitle}>Depuis votre position actuelle</Text>
          <Text style={styles.accessText}>{location.data.montpellierDistance.km} km vers Montpellier · voiture {location.data.montpellierDistance.carHours}h · bus {location.data.montpellierDistance.busHours}h · train {location.data.montpellierDistance.trainHours}h estimé</Text>
        </View>
      )}

      <MapLayerToggle active={layer} onChange={setLayer} />

      <View style={styles.mapFrame}>
        <RealRasterMap center={center} zoom={MAP_ZOOM} width={MAP_WIDTH} height={MAP_HEIGHT}>
          <RoutePolyline points={routePoints} />
          {showTransit && routes.slice(0, 4).map((route: TamRoute, index: number) => <RouteLine key={route.id ?? route.route_id ?? index} route={route} center={center} />)}
          <UserMarker left={userPosition.left} top={userPosition.top} />
          <DestinationMarker left={destinationPosition.left} top={destinationPosition.top} />

          {activeStation && (
            <StationMarker
              station={activeStation}
              left={projectPoint(activeStation, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT).left}
              top={projectPoint(activeStation, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT).top}
              recommended
              onPress={() => {
                setSelectedStation(activeStation);
                setTab('stations');
              }}
            />
          )}

          {showBikes && stationClusters.map((cluster) => (
            cluster.station ? (
              <StationMarker
                key={cluster.key}
                station={cluster.station}
                left={cluster.left}
                top={cluster.top}
                onPress={() => {
                  setSelectedStation(cluster.station ?? null);
                  setTab('stations');
                }}
              />
            ) : (
              <ClusterMarker key={cluster.key} cluster={cluster} onPress={() => setTab('stations')} />
            )
          ))}

          {showParkings && visibleParkings.map((parking: Parking) => {
            const pos = projectPoint(parking, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT);
            return <ParkingMarker key={parking.id} parking={parking} left={pos.left} top={pos.top} />;
          })}

          {showTransit && visibleStops.map((stop) => {
            const pos = projectPoint({ lat: stop.lat, lon: stop.lon }, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT);
            return (
              <TamStopMarker
                key={stop.id}
                stop={stop}
                left={pos.left}
                top={pos.top}
                onPress={() => {
                  setSelectedStop(stop);
                  setTab('transport');
                }}
              />
            );
          })}

          {showTraffic && <View style={[styles.trafficOverlay, traffic.dense && styles.trafficDense]}><Text style={styles.overlayText}>{traffic.label}</Text></View>}
          <View style={styles.decisionOverlay}>
            <Text style={styles.decisionKicker}>Vous etes ici</Text>
            <Text style={styles.decisionTitle}>Station recommandee</Text>
            <Text style={styles.decisionMeta}>{recommended?.durationMinutes ?? localRecommendation.durationMinutes} min · -{localRecommendation.co2SavedKg.toFixed(1)} kg CO2</Text>
            <Pressable onPress={() => startPass('velo')} style={styles.decisionButton}>
              <Text style={styles.decisionButtonText}>{startingPass ? 'Demarrage...' : 'Commencer avec Pass Flow'}</Text>
            </Pressable>
          </View>
        </RealRasterMap>
      </View>

      <BottomSheet>
        <View style={styles.tabs}>
          {(['summary', 'options', 'stations', 'transport', 'pass'] as SheetTab[]).map((item) => (
            <Pressable key={item} onPress={() => setTab(item)} style={[styles.tab, tab === item && styles.tabActive]}>
              <Text style={[styles.tabText, tab === item && styles.tabTextActive]}>{tabLabel(item)}</Text>
            </Pressable>
          ))}
        </View>

        {tab === 'summary' && (
          <Animated.View entering={FadeInUp.duration(220)} style={styles.summary}>
            <View style={styles.summaryTop}>
              <View style={styles.summaryCopy}>
                <Text style={styles.label}>Meilleur choix maintenant</Text>
                <Text style={styles.recoTitle}>{modeIcons[recommended?.mode ?? localRecommendation.mode]} {recommended?.label ?? localRecommendation.label}</Text>
                <Text style={styles.recoMeta}>{recommended?.durationMinutes ?? localRecommendation.durationMinutes} min · -{localRecommendation.co2SavedKg.toFixed(1)} kg CO2</Text>
              </View>
              <ScoreRing score={recommended?.score ?? localRecommendation.score} />
            </View>
            <Text style={styles.reason}>{recommendationReason(localRecommendation.reason, traffic, weather?.precipitation ?? 0)}</Text>
            <Text style={styles.humanHint}>{activeStation ? `${activeStation.name} est la meilleure station : ${activeStation.bikes_available} velos, a environ 4 min.` : 'Recherche de la meilleure station en cours.'}</Text>
            <View style={styles.buttonStack}>
              <TicketActionButton label={journey.isPending ? 'Calcul temps reel...' : 'Recalculer maintenant'} icon="🧭" onPress={() => journey.mutate()} />
              <TicketActionButton label={startingPass ? 'Demarrage...' : 'Commencer ce trajet'} icon="🎫" tone="secondary" onPress={() => startPass('velo')} />
            </View>
          </Animated.View>
        )}

        {tab === 'options' && (
          <View style={styles.optionList}>
            {options.map((option) => <OptionCard key={option.key} option={option} recommended={option.key === (recommended?.mode ?? localRecommendation.mode)} />)}
          </View>
        )}

        {tab === 'stations' && (
          <View style={styles.list}>
            {activeStation && (
              <View style={styles.highlight}>
                <Text style={styles.label}>Station recommandee</Text>
                <Text style={styles.stationTitle}>{activeStation.name}</Text>
                <Text style={styles.body}>{activeStation.bikes_available} velos maintenant · {stationPrediction == null ? 'prediction 30 min indisponible' : `${stationPrediction} velos prevus dans 30 min`}</Text>
                <TicketActionButton label="Prendre un velo" icon="🚲" onPress={() => startPass('velo')} />
              </View>
            )}
            {visibleStations.filter((station) => station.id !== activeStation?.id).map((station: PositionedStation) => (
              <Pressable key={station.id} onPress={() => setSelectedStation(station)} style={styles.rowCard}>
                <View style={[styles.statusDot, { backgroundColor: stationColor(station) }]} />
                <View style={styles.rowCopy}>
                  <Text style={styles.rowTitle}>{station.name}</Text>
                  <Text style={styles.body}>{station.bikes_available} velos · {station.docks_available} bornes libres · {station.distanceKm.toFixed(1)} km</Text>
                </View>
              </Pressable>
            ))}
          </View>
        )}

        {tab === 'transport' && (
          <View style={styles.list}>
            {selectedStop && (
              <View style={styles.highlight}>
                <Text style={styles.label}>Arret selectionne</Text>
                <Text style={styles.stationTitle}>{stopName(selectedStop)}</Text>
                <Text style={styles.body}>Prochain passage : horaire non disponible</Text>
              </View>
            )}
            {visibleStops.length === 0 && <Text style={styles.emptyText}>Activez Bus ou Tram pour voir uniquement les arrets pertinents dans la zone visible.</Text>}
            {visibleStops.map((stop) => (
              <Pressable key={stop.id} onPress={() => setSelectedStop(stop)} style={styles.rowCard}>
                <View style={styles.tamDot}><Text style={styles.tamDotText}>{stop.mode?.includes('tram') ? 'T' : 'B'}</Text></View>
                <View style={styles.rowCopy}>
                  <Text style={styles.rowTitle}>{stopName(stop)}</Text>
                  <Text style={styles.body}>Lignes {lineText(stop)} · {stop.distanceKm.toFixed(1)} km · prochain passage non disponible</Text>
                </View>
              </Pressable>
            ))}
          </View>
        )}

        {tab === 'pass' && (
          <View style={styles.passPane}>
            {ticketStore.activeTicket ? (
              <>
                <Text style={styles.recoTitle}>Pass Flow actif</Text>
                <Text style={styles.body}>Ticket #{ticketStore.activeTicket.ticket_id.slice(0, 8)} · {ticketStore.activeTicket.mode}</Text>
                <TicketActionButton label="Voir mon Pass" icon="🎫" onPress={() => onNavigate?.('pass')} />
              </>
            ) : (
              <>
                <Text style={styles.recoTitle}>Pass Flow pret</Text>
                <Text style={styles.body}>Demarrez ce trajet avec le Pass multimodal.</Text>
                <TicketActionButton label="Commencer ce trajet" icon="🎫" onPress={() => startPass('velo')} />
              </>
            )}
          </View>
        )}
      </BottomSheet>
    </ScrollView>
  );
}

function ClusterMarker({ cluster, onPress }: { cluster: StationCluster; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.clusterMarker, { left: cluster.left, top: cluster.top }]}>
      <Text style={styles.clusterText}>{cluster.count}</Text>
    </Pressable>
  );
}

function getVisiblePoints<T extends { lat: number; lon: number }>(items: T[], center: { lat: number; lon: number }, limit: number): T[] {
  return items
    .filter((item) => isInViewport(item, center))
    .slice(0, limit);
}

function getVisibleTamStops(stops: PositionedStop[], center: { lat: number; lon: number }, userPoint: { lat: number; lon: number }, layer: MapLayer): PositionedStop[] {
  if (layer !== 'bus' && layer !== 'tram') return [];

  const modeStops = stops.filter((stop) => {
    const mode = stop.mode?.toLowerCase() ?? '';
    if (layer === 'tram') return mode.includes('tram') || mode === 'tam';
    if (layer === 'bus') return mode.includes('bus') || mode === 'tam';
    return false;
  });

  return modeStops
    .filter((stop) => isInViewport(stop, center))
    .map((stop) => ({ ...stop, distanceKm: calculateDistanceKm(stop, userPoint) }))
    .sort((a, b) => a.distanceKm - b.distanceKm)
    .slice(0, MAX_TAM_MARKERS);
}

function clusterStations(stations: PositionedStation[], center: { lat: number; lon: number }): StationCluster[] {
  const gridSize = 72;
  const buckets = new Map<string, PositionedStation[]>();

  stations.forEach((station) => {
    const point = projectPoint(station, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT);
    if (!isScreenPointVisible(point)) return;
    const key = `${Math.round(point.left / gridSize)}:${Math.round(point.top / gridSize)}`;
    buckets.set(key, [...(buckets.get(key) ?? []), station]);
  });

  return [...buckets.entries()]
    .slice(0, MAX_CONTEXT_MARKERS)
    .map(([key, bucket]) => {
      const points = bucket.map((station) => projectPoint(station, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT));
      const left = points.reduce((sum, point) => sum + point.left, 0) / points.length;
      const top = points.reduce((sum, point) => sum + point.top, 0) / points.length;
      const bikes = bucket.reduce((sum, station) => sum + station.bikes_available, 0);

      return {
        key,
        count: bucket.length,
        bikes,
        left,
        top,
        station: bucket.length === 1 ? bucket[0] : undefined,
      };
    });
}

function isInViewport(point: { lat: number; lon: number }, center: { lat: number; lon: number }) {
  return isScreenPointVisible(projectPoint(point, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT));
}

function isScreenPointVisible(point: { left: number; top: number }) {
  return point.left >= -40 && point.left <= MAP_WIDTH + 40 && point.top >= -40 && point.top <= MAP_HEIGHT + 40;
}

function RouteLine({ route, center }: { route: TamRoute; center: { lat: number; lon: number } }) {
  if (!route.coordinates?.length) return null;
  const points = route.coordinates.map(([lon, lat]) => projectPoint({ lat, lon }, center, MAP_ZOOM, MAP_WIDTH, MAP_HEIGHT));
  return <RoutePolyline points={points} />;
}

function buildOptions(journeyOptions: JourneyOption[] | undefined, localOptions: Array<{ mode: LocalMode; label: string; score: number; durationMinutes: number; co2SavedKg: number; reason: string }>, now: Date) {
  if (journeyOptions?.length) {
    const transit = journeyOptions.find((option) => option.mode === 'transit');
    const normalized = journeyOptions.map((option) => ({
      key: option.mode,
      icon: modeIcons[option.mode],
      label: option.mode === 'transit' ? 'Tram' : option.label,
      duration: option.durationMinutes,
      co2: option.co2Grams === 0 ? 'CO2 faible' : `${option.co2Grams} g CO2`,
      score: option.score,
      detail: option.mode === 'transit' ? `Prochain depart estime 4 min · arrivee ${arrivalTime(now, option.durationMinutes + 4)} estimee` : option.mode === 'car' ? 'Trafic dense, voiture deconseillee' : 'Calcule par le moteur IA',
      estimated: option.mode === 'transit',
    }));

    return [
      ...normalized,
      {
        key: 'bus',
        icon: '🚌',
        label: 'Bus',
        duration: 19,
        co2: 'CO2 modere',
        score: Math.max(65, transit?.score ?? 72),
        detail: `Prochain depart estime 7 min · arrivee ${arrivalTime(now, 26)} estimee`,
        estimated: true,
      },
    ];
  }

  return [
    ...localOptions.map((option) => ({
      key: option.mode,
      icon: modeIcons[option.mode],
      label: option.mode === 'transit' ? 'Tram' : option.label,
      duration: option.durationMinutes,
      co2: `${option.co2SavedKg.toFixed(1)} kg evites`,
      score: option.score,
      detail: option.reason,
      estimated: true,
    })),
    { key: 'bus', icon: '🚌', label: 'Bus', duration: 19, co2: '0.7 kg evites', score: 74, detail: `Prochain depart estime 7 min · arrivee ${arrivalTime(now, 26)} estimee`, estimated: true },
  ];
}

function OptionCard({ option, recommended }: { option: ReturnType<typeof buildOptions>[number]; recommended: boolean }) {
  return (
    <View style={[styles.optionCard, recommended && styles.optionRecommended]}>
      <Text style={styles.optionIcon}>{option.icon}</Text>
      <View style={styles.optionCopy}>
        <View style={styles.optionHeader}>
          <Text style={styles.optionTitle}>{option.label}</Text>
          {recommended && <Text style={styles.recommendedBadge}>RECOMMANDE</Text>}
        </View>
        <Text style={styles.optionMeta}>{option.duration} min · score {Math.round(option.score)}/100 · {option.co2}</Text>
        <Text style={styles.body}>{option.detail}</Text>
      </View>
    </View>
  );
}

function normalizeStops(stops: TamStop[]): Array<TamStop & { id: string; lat: number; lon: number; mode: string }> {
  return stops
    .map((stop, index) => ({
      ...stop,
      id: stop.id ?? stop.stop_id ?? `tam-${index}`,
      lat: Number(stop.lat ?? stop.stop_lat),
      lon: Number(stop.lon ?? stop.stop_lon),
      mode: stop.mode ?? 'tam',
    }))
    .filter((stop) => Number.isFinite(stop.lat) && Number.isFinite(stop.lon));
}

function getTrafficSignal(hour: number) {
  if ((hour >= 7 && hour < 9) || (hour >= 17 && hour < 20)) return { label: 'Trafic dense, voiture deconseillee', index: 0.78, dense: true };
  if (hour >= 12 && hour < 14) return { label: 'Trafic moyen estime', index: 0.52, dense: false };
  return { label: 'Trafic fluide estime', index: 0.28, dense: false };
}

function weatherLabel(temperature?: number, precipitation?: number) {
  if ((precipitation ?? 0) > 2) return 'Pluie detectee';
  return `${temperature ?? '--'}°C, meteo correcte`;
}

function airLabel(aqi?: number) {
  if ((aqi ?? 3) >= 4) return 'Air degrade aujourd hui';
  return 'Air correct aujourd hui';
}

function recommendationReason(reason: string, traffic: { dense: boolean; label: string }, precipitation: number) {
  if (precipitation > 2) return 'Pluie detectee : tram recommande.';
  if (traffic.dense) return `${reason} ${traffic.label}.`;
  return reason;
}

function arrivalTime(now: Date, minutes: number) {
  const date = new Date(now.getTime() + minutes * 60000);
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function tabLabel(tab: SheetTab) {
  return ({ summary: 'Resume', options: 'Options', stations: 'Stations', transport: 'Transport', pass: 'Pass' })[tab];
}

function stopName(stop: TamStop) {
  return stop.name ?? stop.stop_name ?? 'Arret TAM';
}

function lineText(stop: TamStop) {
  const lines = stop.lines ?? stop.routes;
  if (Array.isArray(lines)) return lines.join(', ');
  return lines || 'non communiquees';
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#eef2f0' },
  content: { padding: 14, paddingBottom: 28, gap: 12, maxWidth: 900, width: '100%', alignSelf: 'center' },
  headerFloating: { zIndex: 5, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.94)', padding: 14, flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center', borderWidth: 1, borderColor: '#e5e7eb' },
  headerCopy: { flex: 1 },
  time: { color: '#10201a', fontSize: 18, fontWeight: '900' },
  context: { color: '#475569', fontSize: 13, marginTop: 4, fontWeight: '800' },
  trackedCity: { color: '#137a4b', fontSize: 12, marginTop: 5, fontWeight: '900' },
  accessCard: { borderRadius: 14, backgroundColor: '#10201a', padding: 13 },
  accessTitle: { color: '#f8fafc', fontSize: 15, fontWeight: '900' },
  accessText: { color: '#dbe8df', fontSize: 13, lineHeight: 19, marginTop: 4, fontWeight: '800' },
  mapFrame: { borderRadius: 20, overflow: 'hidden', borderWidth: 1, borderColor: '#cbd5e1', backgroundColor: '#dbeafe' },
  clusterMarker: { position: 'absolute', width: 44, height: 44, marginLeft: -22, marginTop: -22, borderRadius: 22, backgroundColor: '#10201a', borderWidth: 3, borderColor: '#ffffff', alignItems: 'center', justifyContent: 'center' },
  clusterText: { color: '#a7f3d0', fontSize: 15, fontWeight: '900' },
  decisionOverlay: { position: 'absolute', left: 16, bottom: 16, width: 255, borderRadius: 18, backgroundColor: 'rgba(8,13,18,0.9)', padding: 14, borderWidth: 1, borderColor: 'rgba(167,243,208,0.35)' },
  decisionKicker: { color: '#a7f3d0', fontSize: 12, fontWeight: '900', textTransform: 'uppercase' },
  decisionTitle: { color: '#f8fafc', fontSize: 19, fontWeight: '900', marginTop: 4 },
  decisionMeta: { color: '#d1d5db', fontSize: 14, fontWeight: '800', marginTop: 4 },
  decisionButton: { height: 40, borderRadius: 12, backgroundColor: '#a7f3d0', alignItems: 'center', justifyContent: 'center', marginTop: 10 },
  decisionButtonText: { color: '#07130d', fontSize: 13, fontWeight: '900' },
  trafficOverlay: { position: 'absolute', top: 14, right: 14, borderRadius: 12, backgroundColor: 'rgba(16,32,26,0.88)', paddingHorizontal: 12, paddingVertical: 8 },
  trafficDense: { backgroundColor: 'rgba(153,27,27,0.9)' },
  overlayText: { color: '#f8fafc', fontSize: 12, fontWeight: '900' },
  tabs: { flexDirection: 'row', gap: 6 },
  tab: { flex: 1, minHeight: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#111827' },
  tabActive: { backgroundColor: '#a7f3d0' },
  tabText: { color: '#cbd5e1', fontSize: 11, fontWeight: '900' },
  tabTextActive: { color: '#05070a' },
  summary: { gap: 12 },
  summaryTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  summaryCopy: { flex: 1 },
  label: { color: '#95a1b2', fontSize: 12, textTransform: 'uppercase', fontWeight: '900' },
  recoTitle: { color: '#f8fafc', fontSize: 24, fontWeight: '900', marginTop: 4 },
  recoMeta: { color: '#a7f3d0', fontSize: 15, fontWeight: '900', marginTop: 4 },
  reason: { color: '#d1d5db', fontSize: 15, lineHeight: 22, fontWeight: '800' },
  humanHint: { color: '#a7f3d0', fontSize: 14, lineHeight: 20, fontWeight: '800' },
  buttonStack: { gap: 8 },
  optionList: { gap: 10 },
  optionCard: { borderRadius: 14, backgroundColor: '#111827', borderWidth: 1, borderColor: '#263142', padding: 12, flexDirection: 'row', gap: 12 },
  optionRecommended: { borderColor: '#a7f3d0', backgroundColor: '#102017' },
  optionIcon: { fontSize: 30, width: 36, textAlign: 'center' },
  optionCopy: { flex: 1 },
  optionHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  optionTitle: { color: '#f8fafc', fontSize: 18, fontWeight: '900' },
  optionMeta: { color: '#a7f3d0', fontSize: 13, fontWeight: '900', marginTop: 3 },
  recommendedBadge: { color: '#10201a', backgroundColor: '#a7f3d0', overflow: 'hidden', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4, fontSize: 10, fontWeight: '900' },
  list: { gap: 10 },
  highlight: { borderRadius: 14, backgroundColor: '#102017', borderWidth: 1, borderColor: '#286243', padding: 14, gap: 8 },
  stationTitle: { color: '#f8fafc', fontSize: 23, fontWeight: '900', marginTop: 3 },
  body: { color: '#aeb8c6', fontSize: 14, marginTop: 4, lineHeight: 20, fontWeight: '700' },
  rowCard: { minHeight: 62, flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 14, backgroundColor: '#111827', padding: 12 },
  statusDot: { width: 13, height: 13, borderRadius: 7 },
  tamDot: { width: 32, height: 32, borderRadius: 16, backgroundColor: '#7c3aed', alignItems: 'center', justifyContent: 'center' },
  tamDotText: { color: '#ffffff', fontWeight: '900' },
  rowCopy: { flex: 1 },
  rowTitle: { color: '#f8fafc', fontSize: 16, fontWeight: '900' },
  emptyText: { color: '#cbd5e1', fontSize: 14, lineHeight: 20, fontWeight: '800' },
  passPane: { gap: 10 },
});
