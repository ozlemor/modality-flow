import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  FadeInDown,
  FadeInUp,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { AppButton } from '../components/ui/AppButton';
import { AppCard } from '../components/ui/AppCard';
import { BadgePill } from '../components/ui/BadgePill';
import { LoadingState } from '../components/ui/LoadingState';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Screen } from '../components/ui/Screen';
import { buildLocalRecommendation } from '../features/recommendation/recommendation.logic';
import { useEffectiveLocation } from '../hooks/useEffectiveLocation';
import { useTimeContext } from '../hooks/useTimeContext';
import { TRACKED_DESTINATION } from '../services/location.service';
import { colors, radius, spacing, typography } from '../design/tokens';
import { getAqi, getStations, getWeather } from '../services/mobility.service';
import { EnvironmentContext, Station } from '../types';

type HomeTab = 'today' | 'map' | 'pass' | 'challenges' | 'profile';

const progress = {
  xp: 1640,
  nextLevelXp: 2200,
  streakDays: 4,
  dailyCo2Kg: 1.4,
  badgeProgress: 80,
  level: 'Cycliste regulier',
};

export function HomeScreen({ onNavigate }: { onNavigate?: (tab: HomeTab) => void }) {
  const timeContext = useTimeContext();
  const location = useEffectiveLocation();
  const heroScale = useSharedValue(1);
  const glow = useSharedValue(0.72);

  const { data: weather, isLoading: weatherLoading } = useQuery({
    queryKey: ['weather'],
    queryFn: getWeather,
    refetchInterval: 60000,
  });

  const { data: aqiSignal, isLoading: aqiLoading } = useQuery({
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

  useEffect(() => {
    glow.value = withRepeat(withTiming(1, { duration: 1400 }), -1, true);
  }, [glow]);

  const recommendation = buildLocalRecommendation({
    environment,
    timeContext,
    stations,
  });

  const activeLocation = location.data?.location;
  const trackingMontpellier = location.data?.usesTrackedCityLocation ?? true;
  const xpProgress = Math.round((progress.xp / progress.nextLevelXp) * 100);

  const glowStyle = useAnimatedStyle(() => ({
    opacity: glow.value,
    transform: [{ scale: glow.value }],
  }));

  const heroPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: heroScale.value }],
  }));

  const loading = weatherLoading || aqiLoading || location.isLoading;

  return (
    <Screen>
      <View style={styles.header}>
        <View>
          <Text style={styles.hello}>Bonjour 👋</Text>
          <Text style={styles.headerSubtitle}>{timeContext.time} · {timeContext.periodLabel}</Text>
        </View>
        {trackingMontpellier && <BadgePill label="Ville suivie Montpellier" icon="📍" tone="green" />}
      </View>

      {location.data?.isOutsideMontpellier && location.data.montpellierDistance && (
        <AppCard tone="dark">
          <Text style={styles.outsideTitle}>Vous etes actuellement hors Montpellier</Text>
          <Text style={styles.outsideText}>{location.data.montpellierDistance.label}</Text>
          <Text style={styles.outsideText}>
            Voiture {location.data.montpellierDistance.carHours}h · Bus {location.data.montpellierDistance.busHours}h · Train {location.data.montpellierDistance.trainHours}h
          </Text>
          <Text style={styles.outsideHint}>Ville suivie : Montpellier.</Text>
        </AppCard>
      )}

      {loading ? (
        <LoadingState />
      ) : (
        <Pressable
          onPress={() => onNavigate?.('map')}
          onPressIn={() => {
            heroScale.value = withSpring(0.985);
          }}
          onPressOut={() => {
            heroScale.value = withSpring(1);
          }}
        >
          <Animated.View entering={FadeInDown.duration(420)} style={[styles.heroCard, heroPressStyle]}>
            <Animated.View style={[styles.heroGlow, glowStyle]} />

            <View style={styles.heroTop}>
              <View>
                <Text style={styles.heroEyebrow}>Le meilleur moyen de vous deplacer aujourd hui</Text>
                <Text style={styles.contextText}>{timeContext.mobilityContext}</Text>
              </View>
              <Text style={styles.score}>{recommendation.score}</Text>
            </View>

            <View style={styles.heroMain}>
              <View style={styles.modeBubble}>
                <Text style={styles.modeIcon}>{recommendation.icon}</Text>
              </View>
              <View style={styles.heroCopy}>
                <Text style={styles.heroTitle}>{recommendation.label}</Text>
                <Text style={styles.heroMeta}>{recommendation.durationMinutes} min · {recommendation.co2SavedKg.toFixed(1)} kg de CO2 evitables</Text>
              </View>
            </View>

            <View style={styles.routeBox}>
              <RouteLine icon={recommendation.icon} />
              <View style={styles.routeLabels}>
                <View style={styles.routeLabelBox}>
                  <Text style={styles.routeSmall}>Depuis</Text>
                  <Text style={styles.routeLabel}>{activeLocation?.label ?? 'Comedie - Montpellier'}</Text>
                </View>
                <View style={styles.routeLabelBox}>
                  <Text style={styles.routeSmall}>Vers</Text>
                  <Text style={styles.routeLabel}>{TRACKED_DESTINATION.label}</Text>
                </View>
              </View>
            </View>

            <View style={styles.whyBox}>
              <Text style={styles.whyTitle}>Pourquoi ?</Text>
              <Text style={styles.reason}>{recommendation.reason}</Text>
            </View>

            <View style={styles.heroCta}>
              <Text style={styles.heroCtaText}>Commencer</Text>
            </View>
          </Animated.View>
        </Pressable>
      )}

      <View style={styles.actions}>
        <AppButton label="Voir sur la carte" icon="🗺️" onPress={() => onNavigate?.('map')} />
        <AppButton label="Voir mon Pass" icon="🎫" variant="secondary" onPress={() => onNavigate?.('pass')} />
      </View>

      <Animated.View entering={FadeInUp.delay(90).duration(420)}>
        <AppCard>
          <View style={styles.sectionHeader}>
            <View>
              <Text style={styles.sectionTitle}>Aujourd hui</Text>
              <Text style={styles.sectionSubtitle}>Un petit choix propre, une vraie progression.</Text>
            </View>
            <Text style={styles.streak}>🔥 {progress.streakDays} jours</Text>
          </View>

          <View style={styles.rewardGrid}>
            <Reward label="CO2 economisable" value={`${progress.dailyCo2Kg.toFixed(1)} kg`} icon="🌱" />
            <Reward label="Niveau" value={progress.level} icon="🏆" />
          </View>

          <View style={styles.badgeBox}>
            <View style={styles.badgeTop}>
              <Text style={styles.badgeIcon}>🎯</Text>
              <View style={styles.badgeCopy}>
                <Text style={styles.badgeTitle}>Prochain badge a {progress.badgeProgress}%</Text>
                <Text style={styles.badgeText}>Encore un trajet eco pour debloquer la recompense.</Text>
              </View>
            </View>
            <ProgressBar value={progress.badgeProgress} />
          </View>

          <View style={styles.xpBox}>
            <View style={styles.xpTop}>
              <Text style={styles.xpTitle}>XP du niveau</Text>
              <Text style={styles.xpValue}>{progress.xp}/{progress.nextLevelXp}</Text>
            </View>
            <ProgressBar value={xpProgress} />
          </View>
        </AppCard>
      </Animated.View>
    </Screen>
  );
}

function RouteLine({ icon }: { icon: string }) {
  return (
    <View style={styles.routePreview}>
      <View style={styles.routePoint} />
      <View style={styles.routeLine} />
      <View style={styles.routeMode}>
        <Text style={styles.routeModeIcon}>{icon}</Text>
      </View>
      <View style={styles.routeLine} />
      <View style={styles.routePointEnd} />
    </View>
  );
}

function Reward({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <View style={styles.reward}>
      <Text style={styles.rewardIcon}>{icon}</Text>
      <Text style={styles.rewardValue}>{value}</Text>
      <Text style={styles.rewardLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.md },
  hello: { color: colors.ink, fontSize: typography.title, fontWeight: '900' },
  headerSubtitle: { color: colors.muted, fontSize: typography.body, marginTop: 4, fontWeight: '800' },
  outsideTitle: { color: colors.softText, fontSize: typography.subtitle, fontWeight: '900' },
  outsideText: { color: '#dbe8df', fontSize: typography.body, lineHeight: 23, marginTop: 5, fontWeight: '800' },
  outsideHint: { color: colors.green, fontSize: typography.small, marginTop: spacing.sm, fontWeight: '900' },
  heroCard: {
    minHeight: 474,
    borderRadius: radius.xl,
    backgroundColor: colors.night,
    padding: spacing.lg,
    overflow: 'hidden',
    justifyContent: 'space-between',
  },
  heroGlow: {
    position: 'absolute',
    width: 310,
    height: 310,
    borderRadius: 155,
    right: -98,
    top: -112,
    backgroundColor: 'rgba(74, 222, 128, 0.26)',
  },
  heroTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.md },
  heroEyebrow: { color: '#d7f7e3', fontSize: 14, fontWeight: '900', textTransform: 'uppercase', maxWidth: 250 },
  contextText: { color: '#aebdad', fontSize: typography.small, marginTop: spacing.xs, lineHeight: 18, fontWeight: '700' },
  score: { color: colors.green, fontSize: 34, fontWeight: '900' },
  heroMain: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.xl },
  modeBubble: { width: 92, height: 92, borderRadius: 46, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.green },
  modeIcon: { fontSize: 46 },
  heroCopy: { flex: 1 },
  heroTitle: { color: colors.softText, fontSize: 36, lineHeight: 40, fontWeight: '900' },
  heroMeta: { color: '#dce8de', fontSize: typography.body, lineHeight: 23, marginTop: spacing.xs, fontWeight: '800' },
  routeBox: { marginTop: spacing.xl },
  routePreview: { flexDirection: 'row', alignItems: 'center' },
  routePoint: { width: 18, height: 18, borderRadius: 9, backgroundColor: colors.blue, borderWidth: 3, borderColor: colors.softText },
  routePointEnd: { width: 18, height: 18, borderRadius: 9, backgroundColor: colors.red, borderWidth: 3, borderColor: colors.softText },
  routeLine: { flex: 1, height: 5, borderRadius: 3, backgroundColor: '#314236', marginHorizontal: spacing.sm },
  routeMode: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', backgroundColor: '#24372b' },
  routeModeIcon: { fontSize: 22 },
  routeLabels: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md, marginTop: spacing.sm },
  routeLabelBox: { flex: 1 },
  routeSmall: { color: '#8fa497', fontSize: typography.tiny, textTransform: 'uppercase', fontWeight: '900' },
  routeLabel: { color: colors.softText, fontSize: typography.small, lineHeight: 18, marginTop: 2, fontWeight: '900' },
  whyBox: { borderRadius: radius.md, backgroundColor: 'rgba(255,255,255,0.07)', padding: spacing.md, marginTop: spacing.lg },
  whyTitle: { color: colors.green, fontSize: typography.small, fontWeight: '900', textTransform: 'uppercase' },
  reason: { color: '#e4eee8', fontSize: 17, lineHeight: 24, marginTop: spacing.xs, fontWeight: '700' },
  heroCta: { height: 54, borderRadius: radius.sm, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center', marginTop: spacing.lg },
  heroCtaText: { color: colors.ink, fontSize: typography.body, fontWeight: '900', textTransform: 'uppercase' },
  actions: { flexDirection: 'row', gap: spacing.sm },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md, alignItems: 'flex-start' },
  sectionTitle: { color: colors.ink, fontSize: typography.subtitle, fontWeight: '900' },
  sectionSubtitle: { color: colors.muted, fontSize: typography.body, marginTop: 3 },
  streak: { color: colors.ink, fontSize: 15, fontWeight: '900', backgroundColor: '#ffedd5', paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: radius.sm },
  rewardGrid: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg },
  reward: { flex: 1, borderRadius: radius.md, backgroundColor: colors.cream, padding: spacing.md, minHeight: 110, justifyContent: 'space-between' },
  rewardIcon: { fontSize: 24 },
  rewardValue: { color: colors.ink, fontSize: 20, fontWeight: '900' },
  rewardLabel: { color: colors.muted, fontSize: typography.small, fontWeight: '800' },
  badgeBox: { marginTop: spacing.lg, borderRadius: radius.md, backgroundColor: colors.cream, padding: spacing.md, gap: spacing.md },
  badgeTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  badgeIcon: { fontSize: 28 },
  badgeCopy: { flex: 1 },
  badgeTitle: { color: colors.ink, fontSize: typography.body, fontWeight: '900' },
  badgeText: { color: colors.muted, fontSize: typography.small, marginTop: 2, fontWeight: '700' },
  xpBox: { marginTop: spacing.lg, gap: spacing.sm },
  xpTop: { flexDirection: 'row', justifyContent: 'space-between' },
  xpTitle: { color: colors.ink, fontSize: typography.small, fontWeight: '900' },
  xpValue: { color: colors.greenDeep, fontSize: typography.small, fontWeight: '900' },
});
