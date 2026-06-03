export type TimeContext = {
  currentHour: number;
  periodLabel: string;
  mobilityContext: string;
  isRushHour: boolean;
  isNight: boolean;
};

export function getTimeContext(date = new Date()): TimeContext {
  const currentHour = date.getHours();

  if (currentHour >= 5 && currentHour < 9) {
    return { currentHour, periodLabel: 'Trajet du matin', mobilityContext: 'Rapidite et disponibilite passent devant.', isRushHour: true, isNight: false };
  }
  if (currentHour >= 9 && currentHour < 11) {
    return { currentHour, periodLabel: 'Matin calme', mobilityContext: 'Confort et CO2 passent devant.', isRushHour: false, isNight: false };
  }
  if (currentHour >= 11 && currentHour < 14) {
    return { currentHour, periodLabel: 'Pause midi', mobilityContext: 'Marche et velo sont favorises si la meteo suit.', isRushHour: false, isNight: false };
  }
  if (currentHour >= 14 && currentHour < 17) {
    return { currentHour, periodLabel: 'Apres-midi', mobilityContext: 'On cherche le trajet le plus confortable.', isRushHour: false, isNight: false };
  }
  if (currentHour >= 17 && currentHour < 20) {
    return { currentHour, periodLabel: 'Heure de pointe', mobilityContext: 'Eviter la voiture est plus malin maintenant.', isRushHour: true, isNight: false };
  }
  if (currentHour >= 20 && currentHour < 23) {
    return { currentHour, periodLabel: 'Soiree', mobilityContext: 'Securite et transport deviennent prioritaires.', isRushHour: false, isNight: false };
  }

  return { currentHour, periodLabel: 'Nuit', mobilityContext: 'On evite les longues marches et les choix fatigants.', isRushHour: false, isNight: true };
}
