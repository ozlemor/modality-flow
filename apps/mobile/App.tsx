import React, { useState } from 'react';
import { registerRootComponent } from 'expo';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StatusBar } from 'expo-status-bar';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import Animated, { useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { HomeScreen } from './src/screens/HomeScreen';
import { MapScreen } from './src/screens/MapScreen';
import { Icon, IconName } from './src/components/Icon';
import { ChallengesScreen } from './src/screens/ChallengesScreen';
import { ProfileImpactScreen } from './src/screens/ProfileImpactScreen';
import { PassScreen } from './src/screens/PassScreen';

const queryClient = new QueryClient();
type Tab = 'today' | 'map' | 'pass' | 'challenges' | 'profile';

const tabs: { key: Tab; label: string; icon: IconName }[] = [
  { key: 'today', label: "Aujourd'hui", icon: 'sparkles-outline' },
  { key: 'map', label: 'Carte', icon: 'map-outline' },
  { key: 'pass', label: 'Pass', icon: 'ticket-outline' },
  { key: 'challenges', label: 'Defis', icon: 'trophy' },
  { key: 'profile', label: 'Profil', icon: 'profile' },
];

function Screen({ tab, navigate }: { tab: Tab; navigate: (tab: Tab) => void }) {
  if (tab === 'map') return <MapScreen onNavigate={navigate} />;
  if (tab === 'pass') return <PassScreen />;
  if (tab === 'challenges') return <ChallengesScreen />;
  if (tab === 'profile') return <ProfileImpactScreen />;
  return <HomeScreen onNavigate={navigate} />;
}

function TabButton({ item, active, onPress }: { item: (typeof tabs)[number]; active: boolean; onPress: () => void }) {
  const animated = useAnimatedStyle(() => ({
    transform: [{ scale: withSpring(active ? 1.04 : 1) }],
    opacity: withSpring(active ? 1 : 0.58),
  }));

  return (
    <Pressable onPress={onPress} style={styles.tabHit}>
      <Animated.View style={[styles.tab, active && styles.tabActive, animated]}>
        <Icon name={item.icon} size={20} color={active ? '#f8fbf7' : '#10201a'} />
        {active && <Text style={styles.tabText}>{item.label}</Text>}
      </Animated.View>
    </Pressable>
  );
}

function App() {
  const [tab, setTab] = useState<Tab>('today');

  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <SafeAreaView style={styles.container}>
          <StatusBar style="light" />
          <View style={styles.screen}>
            <Screen tab={tab} navigate={setTab} />
          </View>
          <View style={styles.nav}>
            {tabs.map((item) => (
              <TabButton key={item.key} item={item} active={tab === item.key} onPress={() => setTab(item.key)} />
            ))}
          </View>
        </SafeAreaView>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}

export default App;
registerRootComponent(App);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#05070a' },
  screen: { flex: 1 },
  nav: {
    flexDirection: 'row',
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: '#e7ded0',
    backgroundColor: '#fffaf0',
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  tabHit: { flex: 1, alignItems: 'center' },
  tab: {
    minHeight: 48,
    minWidth: 48,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 7,
    paddingHorizontal: 12,
  },
  tabActive: { backgroundColor: '#10201a' },
  tabText: { color: '#f8fbf7', fontWeight: '900', fontSize: 12 },
});
