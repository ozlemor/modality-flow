import { useEffect, useMemo, useState } from 'react';
import { getTimeContext } from '../features/recommendation/timeContext.logic';

export function useTimeContext() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 15000);
    return () => clearInterval(timer);
  }, []);

  return useMemo(() => {
    const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    return {
      now,
      time,
      ...getTimeContext(now),
    };
  }, [now]);
}
