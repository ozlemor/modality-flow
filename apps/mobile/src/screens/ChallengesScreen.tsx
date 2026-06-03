import { StyleSheet, Text, View } from 'react-native';
import { AppCard } from '../components/ui/AppCard';
import { BadgePill } from '../components/ui/BadgePill';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Screen } from '../components/ui/Screen';
import { colors, spacing, typography } from '../design/tokens';

const challenges = [
  { title: 'Fais un trajet bas carbone aujourd hui', reward: '+50 XP', progress: 0, target: '0/1' },
  { title: '3 trajets velo cette semaine', reward: '+120 XP', progress: 66, target: '2/3' },
  { title: 'Economiser 5 kg CO2', reward: '+90 XP', progress: 78, target: '3.9/5 kg' },
];

const badges = [
  { icon: '🌱', title: 'Premier trajet vert', progress: 100, unlocked: true },
  { icon: '🚲', title: 'Cycliste regulier', progress: 78, unlocked: false },
  { icon: '🌍', title: 'Heros anti-CO2', progress: 52, unlocked: false },
];

export function ChallengesScreen() {
  return (
    <Screen>
      <View>
        <Text style={styles.title}>Defis</Text>
        <Text style={styles.subtitle}>Gagne de l XP en bougeant mieux.</Text>
      </View>

      <AppCard tone="green">
        <BadgePill label="Defi du jour" icon="⚡" tone="dark" />
        <Text style={styles.heroTitle}>Un trajet sans voiture aujourd hui</Text>
        <Text style={styles.heroBody}>Recompense: +50 XP et ta serie continue.</Text>
        <ProgressBar value={0} />
      </AppCard>

      <View style={styles.list}>
        {challenges.map((challenge) => (
          <AppCard key={challenge.title}>
            <View style={styles.challengeTop}>
              <Text style={styles.challengeTitle}>{challenge.title}</Text>
              <Text style={styles.reward}>{challenge.reward}</Text>
            </View>
            <Text style={styles.target}>{challenge.target}</Text>
            <ProgressBar value={challenge.progress} />
          </AppCard>
        ))}
      </View>

      <Text style={styles.sectionTitle}>Badges</Text>
      <View style={styles.badges}>
        {badges.map((badge) => (
          <AppCard key={badge.title}>
            <View style={styles.badgeRow}>
              <Text style={styles.badgeIcon}>{badge.icon}</Text>
              <View style={styles.badgeText}>
                <Text style={styles.badgeTitle}>{badge.title}</Text>
                <Text style={styles.badgeState}>{badge.unlocked ? 'Debloque' : `${badge.progress}%`}</Text>
              </View>
            </View>
            <ProgressBar value={badge.progress} color={badge.unlocked ? colors.greenDeep : colors.blue} />
          </AppCard>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { color: colors.ink, fontSize: typography.title, fontWeight: '900' },
  subtitle: { color: colors.muted, fontSize: typography.body, marginTop: 4, fontWeight: '700' },
  heroTitle: { color: colors.ink, fontSize: 28, fontWeight: '900', marginTop: spacing.md, lineHeight: 32 },
  heroBody: { color: colors.muted, fontSize: typography.body, marginVertical: spacing.md, lineHeight: 23 },
  list: { gap: spacing.sm },
  challengeTop: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
  challengeTitle: { color: colors.ink, fontSize: typography.body, fontWeight: '900', flex: 1 },
  reward: { color: colors.greenDeep, fontSize: typography.small, fontWeight: '900' },
  target: { color: colors.muted, fontSize: typography.small, marginVertical: spacing.sm, fontWeight: '800' },
  sectionTitle: { color: colors.ink, fontSize: typography.subtitle, fontWeight: '900' },
  badges: { gap: spacing.sm },
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginBottom: spacing.md },
  badgeIcon: { fontSize: 34 },
  badgeText: { flex: 1 },
  badgeTitle: { color: colors.ink, fontSize: typography.body, fontWeight: '900' },
  badgeState: { color: colors.muted, fontSize: typography.small, marginTop: 3, fontWeight: '800' },
});
