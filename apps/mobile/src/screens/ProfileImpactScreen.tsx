import { Pressable, StyleSheet, Text, View } from 'react-native';
import { AppCard } from '../components/ui/AppCard';
import { BadgePill } from '../components/ui/BadgePill';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Screen } from '../components/ui/Screen';
import { StatCard } from '../components/ui/StatCard';
import { colors, radius, spacing, typography } from '../design/tokens';

export function ProfileImpactScreen() {
  return (
    <Screen>
      <AppCard tone="dark">
        <View style={styles.profileTop}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>🙂</Text>
          </View>
          <View style={styles.profileCopy}>
            <Text style={styles.name}>Niveau 4</Text>
            <Text style={styles.profileSub}>Coach eco-mobilite en progression</Text>
          </View>
          <BadgePill label="3 jours" icon="🔥" tone="orange" />
        </View>
        <Text style={styles.xp}>1 240 XP</Text>
        <ProgressBar value={62} color={colors.green} />
      </AppCard>

      <Text style={styles.sectionTitle}>Ton impact</Text>
      <View style={styles.statsRow}>
        <StatCard icon="🌍" value="18.4 kg" label="CO2 economise" />
        <StatCard icon="🌿" value="24" label="trajets eco" />
      </View>
      <View style={styles.statsRow}>
        <StatCard icon="🚶" value="210 min" label="minutes actives" />
        <StatCard icon="🚗" value="9" label="voitures evitees" />
      </View>

      <AppCard>
        <Text style={styles.sectionTitle}>Preferences</Text>
        <Preference label="Je prefere le velo" active />
        <Preference label="Eviter la voiture" active />
        <Preference label="Mode simple" />
        <Preference label="Texte plus grand" />
      </AppCard>
    </Screen>
  );
}

function Preference({ label, active = false }: { label: string; active?: boolean }) {
  return (
    <Pressable style={styles.preference}>
      <Text style={styles.preferenceText}>{label}</Text>
      <View style={[styles.toggle, active && styles.toggleActive]}>
        <View style={[styles.toggleKnob, active && styles.toggleKnobActive]} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  profileTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 34 },
  profileCopy: { flex: 1 },
  name: { color: colors.softText, fontSize: typography.subtitle, fontWeight: '900' },
  profileSub: { color: '#c6d7cc', fontSize: typography.small, marginTop: 4, fontWeight: '700' },
  xp: { color: colors.softText, fontSize: 34, fontWeight: '900', marginVertical: spacing.md },
  sectionTitle: { color: colors.ink, fontSize: typography.subtitle, fontWeight: '900' },
  statsRow: { flexDirection: 'row', gap: spacing.sm },
  preference: { minHeight: 56, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: colors.line },
  preferenceText: { color: colors.ink, fontSize: typography.body, fontWeight: '800' },
  toggle: { width: 52, height: 30, borderRadius: radius.sm, backgroundColor: '#d9d1c4', padding: 3 },
  toggleActive: { backgroundColor: colors.greenDeep },
  toggleKnob: { width: 24, height: 24, borderRadius: 12, backgroundColor: colors.surfaceStrong },
  toggleKnobActive: { marginLeft: 22 },
});
