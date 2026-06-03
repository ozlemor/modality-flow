import { useMutation, useQuery } from '@tanstack/react-query';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import { Card } from '../components/Card';
import { Icon, IconName } from '../components/Icon';
import { buildLocalRecommendation, LocalMode } from '../features/recommendation/recommendation.logic';
import { useEffectiveLocation } from '../hooks/useEffectiveLocation';
import { useTimeContext } from '../hooks/useTimeContext';
import { api } from '../services/api';
import { getAqi, getStations, getWeather } from '../services/mobility.service';
import { TRACKED_DESTINATION } from '../services/location.service';
import { EnvironmentContext, JourneyOption, JourneyResponse, Station } from '../types';

const modeIcon: Record<JourneyOption['mode'], IconName> = {
  bike: 'bicycle-outline',
  walk: 'walk-outline',
  transit: 'train-outline',
  car: 'car-outline',
};

const modeCopy: Record<LocalMode, string> = {
  bike: 'Velo',
  walk: 'Marche',
  transit: 'Tram / bus',
  car: 'Voiture',
};

export function JourneyScreen() {
  const timeContext = useTimeContext();
  const location = useEffectiveLocation();

  const { data: weather } = useQuery({
    queryKey: ['weather'],
    queryFn: getWeather,
    refetchInterval: 60000,
  });

  const { data: aqiSignal } = useQuery({
    queryKey: ['aqi'],
    queryFn: getAqi,
    refetchInterval: 60000,
  });

  const { data: stations } = useQuery<Station[]>({
    queryKey: ['stations'],
    queryFn: getStations,
    refetchInterval: 30000,
  });

  const environment: EnvironmentContext = {
    hour: timeContext.currentHour,
    label: timeContext.periodLabel,
    temperature: weather?.temperature ?? 20,
    precipitation: weather?.precipitation ?? 0,
    windSpeed: weather?.windSpeed ?? weather?.wind_speed ?? 10,
    aqi: aqiSignal?.indice_qualite ?? aqiSignal?.aqi ?? 3,
    trafficIndex: timeContext.isRushHour ? 0.78 : 0.32,
    bikeComfort: 'good',
    recommendationReason: '',
    updatedAt: new Date().toISOString(),
  };

  const localRecommendation = buildLocalRecommendation({ environment, timeContext, stations });
  const effectiveLocation = location.data?.location;

  const journey = useMutation<JourneyResponse>({
    mutationFn: async () => {
      const origin = effectiveLocation ?? { lat: 43.6086, lon: 3.8795 };
      return (await api.post('/journey', {
        lat_a: origin.lat,
        lon_a: origin.lon,
        lat_b: TRACKED_DESTINATION.lat,
        lon_b: TRACKED_DESTINATION.lon,
        temperature: environment.temperature,
        precipitation: environment.precipitation,
        wind_speed: environment.windSpeed,
        indice_qualite: environment.aqi,
        heure: timeContext.currentHour,
      })).data;
    },
  });

  const options = journey.data?.options;
  const recommendedMode = journey.data?.recommended.mode ?? localRecommendation.mode;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Votre trajet</Text>
          <Text style={styles.subtitle}>{timeContext.time} · {timeContext.periodLabel}</Text>
        </View>
        {location.data?.usesTrackedCityLocation && (
          <View style={styles.trackedBadge}>
            <Text style={styles.trackedText}>Ville suivie Montpellier</Text>
          </View>
        )}
      </View>

      <Card elevated>
        <Text style={styles.label}>Depart</Text>
        <Text style={styles.place}>{effectiveLocation?.label ?? 'Comedie - Montpellier'}</Text>
        <View style={styles.connector}>
          <Icon name="arrow-down" color="#a7f3d0" size={18} />
        </View>
        <Text style={styles.label}>Arrivee</Text>
        <Text style={styles.place}>{TRACKED_DESTINATION.label}</Text>
        <Text style={styles.helper}>{location.data?.message ?? 'On prepare une position fluide pour Montpellier.'}</Text>
      </Card>

      <Pressable style={styles.cta} onPress={() => journey.mutate()} disabled={journey.isPending}>
        <Icon name="sparkles-outline" color="#05070a" size={20} />
        <Text style={styles.ctaText}>{journey.isPending ? 'Calcul en cours...' : 'Calculer mon trajet'}</Text>
      </Pressable>

      <Animated.View entering={FadeInUp.duration(420)} style={styles.recoCard}>
        <View style={styles.recoTop}>
          <View style={styles.bigIcon}>
            <Icon name={modeIcon[recommendedMode]} color="#05070a" size={34} />
          </View>
          <View style={styles.recoCopy}>
            <Text style={styles.label}>Meilleure proposition</Text>
            <Text style={styles.recoTitle}>{journey.data?.recommended.label ?? localRecommendation.label}</Text>
            <Text style={styles.recoBody}>
              {journey.data?.recommended.durationMinutes ?? localRecommendation.durationMinutes} min · {co2Text(journey.data?.recommended, localRecommendation.co2SavedKg)}
            </Text>
          </View>
        </View>
        <Text style={styles.explain}>
          {journey.data?.recommended ? railwayReason(journey.data.recommended.mode, environment, timeContext.periodLabel) : localRecommendation.reason}
        </Text>
        {journey.data?.bestStation && (
          <Text style={styles.stationHint}>
            Station conseillee : {journey.data.bestStation.name}. Prediction dans 30 min : {journey.data.prediction.predicted_bikes_30min} velos.
          </Text>
        )}
      </Animated.View>

      <View style={styles.options}>
        {(options ?? localRecommendation.options).map((option) => (
          'timeline' in option ? (
            <OptionCard
              key={option.mode}
              option={option}
              recommended={option.mode === recommendedMode}
              reason={railwayReason(option.mode, environment, timeContext.periodLabel)}
            />
          ) : (
            <LocalOptionCard key={option.mode} option={option} recommended={option.mode === recommendedMode} />
          )
        ))}
      </View>
    </ScrollView>
  );
}

function OptionCard({ option, recommended, reason }: { option: JourneyOption; recommended: boolean; reason: string }) {
  return (
    <Card elevated={recommended}>
      <View style={styles.optionTop}>
        <View style={styles.optionName}>
          <Icon name={modeIcon[option.mode]} color="#e6edf7" size={30} />
          <View>
            <Text style={styles.optionTitle}>{option.label}</Text>
            <Text style={styles.body}>{reason}</Text>
          </View>
        </View>
        {recommended && <Text style={styles.recommended}>RECOMMANDE</Text>}
      </View>
      <View style={styles.optionMetrics}>
        <Metric label="Temps" value={`${option.durationMinutes} min`} />
        <Metric label="Impact" value={option.co2Grams === 0 ? 'Tres bas' : `${Math.round(option.co2Grams)} g`} />
        <Metric label="Score" value={`${option.score}/100`} />
      </View>
      <View style={styles.timeline}>
        {option.timeline.map((leg) => (
          <View key={`${option.mode}-${leg.label}`} style={styles.leg}>
            <View style={styles.legDot} />
            <Text style={styles.legText}>{leg.label} · {leg.minutes} min</Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

function LocalOptionCard({
  option,
  recommended,
}: {
  option: { mode: LocalMode; label: string; icon: string; score: number; durationMinutes: number; co2SavedKg: number; reason: string };
  recommended: boolean;
}) {
  return (
    <Card elevated={recommended}>
      <View style={styles.optionTop}>
        <View style={styles.optionName}>
          <Text style={styles.localIcon}>{option.icon}</Text>
          <View>
            <Text style={styles.optionTitle}>{modeCopy[option.mode]}</Text>
            <Text style={styles.body}>{option.reason}</Text>
          </View>
        </View>
        {recommended && <Text style={styles.recommended}>RECOMMANDE</Text>}
      </View>
      <View style={styles.optionMetrics}>
        <Metric label="Temps" value={`${option.durationMinutes} min`} />
        <Metric label="CO2 evite" value={`${option.co2SavedKg.toFixed(1)} kg`} />
        <Metric label="Score" value={`${option.score}/100`} />
      </View>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

function co2Text(option: JourneyOption | undefined, fallbackKg: number) {
  if (!option) return `${fallbackKg.toFixed(1)} kg de CO2 evitables`;
  if (option.mode === 'car') return '0 kg economise';
  return `${Math.max(0.1, (1200 - option.co2Grams) / 1000).toFixed(1)} kg de CO2 evitables`;
}

function railwayReason(mode: JourneyOption['mode'], environment: EnvironmentContext | undefined, period: string) {
  if ((environment?.precipitation ?? 0) > 2 && mode === 'transit') return 'Il pleut, le tram est plus confortable.';
  if ((environment?.aqi ?? 3) >= 4 && mode === 'transit') return 'Air moyen, le transport public est plus doux.';
  if (period === 'Heure de pointe' && mode !== 'car') return 'Heure de pointe, on evite la voiture.';
  if (mode === 'bike') return 'Bon equilibre entre rapidite, impact et disponibilite velo.';
  if (mode === 'walk') return 'Simple, lisible, sans emission.';
  if (mode === 'car') return 'Option de secours, moins bonne pour le score.';
  return 'Trajet confortable et fiable maintenant.';
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#05070a' },
  content: { padding: 18, paddingBottom: 28, gap: 14, maxWidth: 900, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  title: { color: '#f8fafc', fontSize: 30, fontWeight: '900' },
  subtitle: { color: '#8d98a8', marginTop: 4, fontSize: 14, fontWeight: '800' },
  trackedBadge: { borderRadius: 8, backgroundColor: '#a7f3d0', paddingHorizontal: 10, paddingVertical: 7 },
  trackedText: { color: '#05070a', fontSize: 12, fontWeight: '900' },
  label: { color: '#95a1b2', fontSize: 12, textTransform: 'uppercase', fontWeight: '900' },
  place: { color: '#f8fafc', fontSize: 22, fontWeight: '900', marginTop: 7 },
  connector: { height: 34, alignItems: 'flex-start', justifyContent: 'center' },
  helper: { color: '#a7f3d0', fontSize: 13, lineHeight: 19, marginTop: 12, fontWeight: '800' },
  cta: { height: 56, borderRadius: 8, backgroundColor: '#a7f3d0', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8 },
  ctaText: { color: '#05070a', fontWeight: '900', fontSize: 16, textTransform: 'uppercase' },
  recoCard: { borderRadius: 8, backgroundColor: '#102017', padding: 18, borderWidth: 1, borderColor: '#286243' },
  recoTop: { flexDirection: 'row', gap: 14, alignItems: 'center' },
  bigIcon: { width: 70, height: 70, borderRadius: 35, backgroundColor: '#a7f3d0', alignItems: 'center', justifyContent: 'center' },
  recoCopy: { flex: 1 },
  recoTitle: { color: '#f8fafc', fontSize: 28, lineHeight: 32, fontWeight: '900', marginTop: 3 },
  recoBody: { color: '#d8fff0', fontSize: 16, lineHeight: 22, marginTop: 4, fontWeight: '800' },
  explain: { color: '#d8fff0', fontSize: 15, lineHeight: 22, marginTop: 16, fontWeight: '700' },
  stationHint: { color: '#a7f3d0', fontSize: 13, lineHeight: 19, marginTop: 10, fontWeight: '800' },
  options: { gap: 12 },
  optionTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  optionName: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12 },
  localIcon: { fontSize: 30, width: 36, textAlign: 'center' },
  optionTitle: { color: '#f8fafc', fontSize: 22, fontWeight: '900' },
  recommended: { color: '#05070a', backgroundColor: '#a7f3d0', overflow: 'hidden', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, fontSize: 10, fontWeight: '900' },
  body: { color: '#aeb8c6', fontSize: 14, lineHeight: 20, marginTop: 4 },
  optionMetrics: { flexDirection: 'row', gap: 10, marginTop: 16 },
  metric: { flex: 1, minHeight: 70, borderRadius: 8, backgroundColor: '#0d131b', padding: 10, justifyContent: 'space-between' },
  metricValue: { color: '#f8fafc', fontSize: 17, fontWeight: '900' },
  metricLabel: { color: '#8d98a8', fontSize: 11, fontWeight: '800' },
  timeline: { marginTop: 14, gap: 8 },
  leg: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  legDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#a7f3d0' },
  legText: { color: '#c6d0de', fontSize: 13 },
});
