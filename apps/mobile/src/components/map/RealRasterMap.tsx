import { ReactNode, useMemo } from 'react';
import { Image, StyleSheet, View } from 'react-native';

export type MapPoint = {
  lat: number;
  lon: number;
};

type Tile = {
  x: number;
  y: number;
  z: number;
  left: number;
  top: number;
};

const TILE_SIZE = 256;

export function projectPoint(point: MapPoint, center: MapPoint, zoom: number, width: number, height: number) {
  const centerWorld = latLonToWorld(center.lat, center.lon, zoom);
  const pointWorld = latLonToWorld(point.lat, point.lon, zoom);

  return {
    left: width / 2 + pointWorld.x - centerWorld.x,
    top: height / 2 + pointWorld.y - centerWorld.y,
  };
}

export function RealRasterMap({
  center,
  zoom = 14,
  width = 900,
  height = 520,
  children,
}: {
  center: MapPoint;
  zoom?: number;
  width?: number;
  height?: number;
  children: ReactNode;
}) {
  const tiles = useMemo(() => getTiles(center, zoom, width, height), [center, zoom, width, height]);

  return (
    <View style={[styles.map, { height }]}>
      {tiles.map((tile) => (
        <Image
          key={`${tile.z}-${tile.x}-${tile.y}`}
          source={{ uri: `https://tile.openstreetmap.org/${tile.z}/${tile.x}/${tile.y}.png` }}
          style={[styles.tile, { left: tile.left, top: tile.top }]}
        />
      ))}
      <View style={StyleSheet.absoluteFill}>{children}</View>
    </View>
  );
}

function getTiles(center: MapPoint, zoom: number, width: number, height: number) {
  const centerWorld = latLonToWorld(center.lat, center.lon, zoom);
  const startX = Math.floor((centerWorld.x - width / 2) / TILE_SIZE);
  const endX = Math.floor((centerWorld.x + width / 2) / TILE_SIZE);
  const startY = Math.floor((centerWorld.y - height / 2) / TILE_SIZE);
  const endY = Math.floor((centerWorld.y + height / 2) / TILE_SIZE);
  const max = 2 ** zoom;
  const tiles: Tile[] = [];

  for (let x = startX; x <= endX; x += 1) {
    for (let y = startY; y <= endY; y += 1) {
      const wrappedX = ((x % max) + max) % max;
      tiles.push({
        x: wrappedX,
        y,
        z: zoom,
        left: x * TILE_SIZE - centerWorld.x + width / 2,
        top: y * TILE_SIZE - centerWorld.y + height / 2,
      });
    }
  }

  return tiles;
}

function latLonToWorld(lat: number, lon: number, zoom: number) {
  const scale = TILE_SIZE * 2 ** zoom;
  const sinLat = Math.sin((lat * Math.PI) / 180);
  return {
    x: ((lon + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale,
  };
}

const styles = StyleSheet.create({
  map: { width: '100%', borderRadius: 18, overflow: 'hidden', backgroundColor: '#dbeafe' },
  tile: { position: 'absolute', width: TILE_SIZE, height: TILE_SIZE },
});
