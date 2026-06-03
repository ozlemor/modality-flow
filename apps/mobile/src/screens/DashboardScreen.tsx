import { useQuery } from '@tanstack/react-query';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Card } from '../components/Card';
import { Icon, IconName } from '../components/Icon';
import { api } from '../services/api';

export function DashboardScreen() {
  const { data } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get('/billetterie/stats')).data,
    refetchInterval: 20000,
  });

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.title}>Dashboard KPI</Text>
        <Text style={styles.status}>{data?.status ?? 'sync'}</Text>
      </View>
      <View style={styles.grid}>
        <Kpi icon="bicycle-outline" label="Velos disponibles" value={data?.bikesAvailable ?? '--'} />
        <Kpi icon="alert-circle-outline" label="Stations critiques" value={data?.criticalStations ?? '--'} warning />
        <Kpi icon="car-outline" label="Parkings dispo" value={data?.parkingPlaces ?? '--'} />
        <Kpi icon="leaf-outline" label="Qualite air" value={`${data?.aqi ?? '--'}/6`} />
      </View>

      <Card elevated>
        <Text style={styles.label}>Operations</Text>
        <Text style={styles.opsTitle}>Priorites temps reel</Text>
        <View style={styles.alertRow}>
          <Icon name="notifications-outline" color="#fbbf24" size={20} />
          <Text style={styles.body}>Alerte si une station passe sous 2 velos.</Text>
        </View>
        <View style={styles.alertRow}>
          <Icon name="cloud-outline" color="#38bdf8" size={20} />
          <Text style={styles.body}>Bascule vers transport public si pollution ou pluie augmentent.</Text>
        </View>
      </Card>
    </ScrollView>
  );
}

function Kpi({ icon, label, value, warning = false }: { icon: IconName; label: string; value: string | number; warning?: boolean }) {
  return (
    <Card>
      <Icon name={icon} color={warning ? '#fbbf24' : '#a7f3d0'} size={24} />
      <Text style={styles.kpiValue}>{value}</Text>
      <Text style={styles.kpiLabel}>{label}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#05070a' },
  content: { padding: 18, paddingBottom: 28, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { color: '#f8fafc', fontSize: 28, fontWeight: '900' },
  status: { color: '#05070a', backgroundColor: '#a7f3d0', borderRadius: 8, overflow: 'hidden', paddingHorizontal: 10, paddingVertical: 6, fontWeight: '900' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  kpiValue: { color: '#f8fafc', fontSize: 25, fontWeight: '900', marginTop: 12 },
  kpiLabel: { color: '#aeb8c6', fontSize: 13, marginTop: 6 },
  label: { color: '#95a1b2', fontSize: 12, textTransform: 'uppercase', fontWeight: '800' },
  opsTitle: { color: '#f8fafc', fontSize: 22, fontWeight: '900', marginTop: 8 },
  alertRow: { flexDirection: 'row', gap: 10, alignItems: 'center', marginTop: 12 },
  body: { flex: 1, color: '#aeb8c6', fontSize: 14, lineHeight: 20 },
});
