import { useQuery } from '@tanstack/react-query';
import { getEffectiveUserLocation } from '../services/location.service';

export function useEffectiveLocation() {
  return useQuery({
    queryKey: ['effective-location'],
    queryFn: getEffectiveUserLocation,
    staleTime: 60000,
    retry: false,
  });
}
