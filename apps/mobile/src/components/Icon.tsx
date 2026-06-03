import { StyleSheet, Text } from 'react-native';

const glyphs: Record<string, string> = {
  'sparkles-outline': '✨',
  'map-outline': '🗺️',
  'navigate-outline': '🧭',
  'analytics-outline': '🌱',
  'bicycle-outline': '🚲',
  'leaf-outline': '🌿',
  'warning-outline': '⚠️',
  'time-outline': '⏱️',
  'thermometer-outline': '☀️',
  'rainy-outline': '🌧️',
  'speedometer-outline': '🚦',
  'car-outline': '🚗',
  'radio-outline': '📡',
  'globe-outline': '🌍',
  'chevron-forward': '›',
  'arrow-down': '↓',
  'walk-outline': '🚶',
  'train-outline': '🚋',
  'alert-circle-outline': '⚠️',
  'notifications-outline': '🔔',
  'cloud-outline': '☁️',
  'options-outline': '⚙️',
  'location-outline': '📍',
  'flash-outline': '⚡',
  'shield-checkmark-outline': '✅',
  'swap-horizontal-outline': '↔️',
  'ticket-outline': '🎫',
  trophy: '🏆',
  fire: '🔥',
  profile: '🙂',
};

export type IconName = keyof typeof glyphs | string;

export function Icon({ name, size = 18, color = '#10201a' }: { name: IconName; size?: number; color?: string }) {
  return <Text style={[styles.icon, { color, fontSize: size, minWidth: size + 4 }]}>{glyphs[name] ?? '•'}</Text>;
}

const styles = StyleSheet.create({
  icon: {
    textAlign: 'center',
    lineHeight: 30,
  },
});
