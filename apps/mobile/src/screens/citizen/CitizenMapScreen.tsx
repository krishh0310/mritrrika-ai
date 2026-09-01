import type { RouteProp } from "@react-navigation/native";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useMemo, useState } from "react";
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View,
} from "react-native";
import Svg, { Path } from "react-native-svg";

import {
  useLocations, useVillageParcels, type ParcelFeatureCollection,
} from "../../api/queries";
import {
  Button, Card, EmptyState, ErrorText, Eyebrow, Identifier, SyntheticNotice,
} from "../../components/ui";
import type { CitizenStackParams } from "../../navigation";
import { colors, radius, spacing } from "../../theme";

/**
 * §59 CitizenMap — the cadastre, drawn from the server's own geometry.
 *
 * Deliberately not a tiled basemap. A parcel map answers "which shape is mine,
 * and what is next to it", and that needs the cadastral boundaries the API
 * already serves as GeoJSON (§53) -- not satellite imagery, which a field
 * phone would spend its data allowance fetching. Drawing the polygons directly
 * also means the map works with no network once the village is loaded, and
 * pins nothing to a tile provider's idea of where a boundary lies.
 *
 * The projection is equirectangular with a cos(latitude) correction on the
 * longitude axis. Across a single village -- a few kilometres -- that is
 * visually exact, and it keeps parcels the right shape instead of stretching
 * them east-west the way a raw lon/lat plot does.
 */

const CANVAS = 320;
const PADDING = 8;

type Ring = [number, number][];

/** Both Polygon and MultiPolygon flatten to "a list of rings to draw". */
function ringsOf(geometry: { type: string; coordinates: unknown }): Ring[] {
  if (geometry.type === "Polygon") return geometry.coordinates as Ring[];
  if (geometry.type === "MultiPolygon") {
    return (geometry.coordinates as Ring[][]).flat();
  }
  return [];
}

type Shape = {
  parcelId: string;
  khasra: string;
  path: string;
};

type Projected = { shapes: Shape[]; empty: boolean };

function project(collection: ParcelFeatureCollection | undefined): Projected {
  const features = collection?.features ?? [];
  if (features.length === 0) return { shapes: [], empty: true };

  let minLon = Infinity, minLat = Infinity;
  let maxLon = -Infinity, maxLat = -Infinity;

  for (const feature of features) {
    for (const ring of ringsOf(feature.geometry)) {
      for (const [lon, lat] of ring) {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      }
    }
  }

  if (!Number.isFinite(minLon)) return { shapes: [], empty: true };

  // Longitude degrees are shorter than latitude degrees away from the equator.
  // Without this a village at 27°N comes out stretched by about 11%.
  const midLat = ((minLat + maxLat) / 2) * (Math.PI / 180);
  const lonScale = Math.cos(midLat) || 1;

  const width = Math.max((maxLon - minLon) * lonScale, 1e-9);
  const height = Math.max(maxLat - minLat, 1e-9);
  const usable = CANVAS - PADDING * 2;
  // One scale for both axes, so the shapes stay true rather than filling
  // the box.
  const scale = Math.min(usable / width, usable / height);
  const offsetX = PADDING + (usable - width * scale) / 2;
  const offsetY = PADDING + (usable - height * scale) / 2;

  const toX = (lon: number) => offsetX + (lon - minLon) * lonScale * scale;
  // SVG y grows downward; latitude grows upward. Flip it or north is at the
  // bottom.
  const toY = (lat: number) => offsetY + (maxLat - lat) * scale;

  const shapes: Shape[] = [];
  for (const feature of features) {
    const path = ringsOf(feature.geometry)
      .map(
        (ring) =>
          ring
            .map(
              ([lon, lat], index) =>
                `${index === 0 ? "M" : "L"}${toX(lon).toFixed(2)} ${toY(lat).toFixed(2)}`,
            )
            .join(" ") + " Z",
      )
      .join(" ");

    if (!path) continue;
    shapes.push({
      parcelId: String(feature.properties.parcel_id ?? ""),
      khasra: String(feature.properties.khasra_number ?? "—"),
      path,
    });
  }

  return { shapes, empty: shapes.length === 0 };
}

export function CitizenMapScreen() {
  const { params } = useRoute<RouteProp<CitizenStackParams, "CitizenMap">>();
  const navigation =
    useNavigation<NativeStackNavigationProp<CitizenStackParams>>();

  const villages = useLocations("VILLAGE");
  const [chosen, setChosen] = useState<string | null>(params?.villageId ?? null);

  // Falling back to the first village means the screen shows a map on arrival
  // rather than an empty frame and a picker.
  const villageId = chosen ?? villages.data?.locations[0]?.location_id ?? null;
  const villageName =
    villages.data?.locations.find((v) => v.location_id === villageId)?.name ??
    params?.villageName ??
    null;

  const parcels = useVillageParcels(villageId);
  const { shapes, empty } = useMemo(() => project(parcels.data), [parcels.data]);

  const [selected, setSelected] = useState<string | null>(params?.highlight ?? null);
  const active = shapes.find((shape) => shape.parcelId === selected) ?? null;

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Eyebrow>Village</Eyebrow>
        <Text style={styles.village}>{villageName ?? "Choose a village"}</Text>
        <SyntheticNotice />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={styles.chips}>
          {(villages.data?.locations ?? []).map((village) => {
            const on = village.location_id === villageId;
            return (
              <Pressable
                key={village.location_id}
                onPress={() => {
                  setChosen(village.location_id);
                  setSelected(null);
                }}
                accessibilityRole="button"
                accessibilityState={{ selected: on }}
                style={[styles.chip, on && styles.chipOn]}
              >
                <Text style={[styles.chipLabel, on && styles.chipLabelOn]}>
                  {village.name}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </ScrollView>

      <Card style={styles.mapCard}>
        {parcels.isPending && villageId ? (
          <View style={styles.canvasPlaceholder}>
            <ActivityIndicator color={colors.navy} />
          </View>
        ) : parcels.isError ? (
          <ErrorText>Could not load the parcels for this village.</ErrorText>
        ) : empty ? (
          <EmptyState
            title="No mapped parcels"
            description="This village has no cadastral geometry on file."
          />
        ) : (
          <Svg width={CANVAS} height={CANVAS} style={styles.canvas}>
            {shapes.map((shape) => {
              const on = shape.parcelId === selected;
              return (
                <Path
                  key={shape.parcelId}
                  d={shape.path}
                  fill={on ? colors.warm : colors.sand100}
                  fillOpacity={on ? 0.85 : 1}
                  stroke={on ? colors.burnt : colors.sand300}
                  strokeWidth={on ? 2 : 1}
                  onPress={() => setSelected(shape.parcelId)}
                />
              );
            })}
          </Svg>
        )}
      </Card>

      {active ? (
        <Card style={{ gap: spacing.xs }}>
          <Eyebrow>Selected parcel</Eyebrow>
          <Text style={styles.khasra}>Khasra {active.khasra}</Text>
          <Identifier>{active.parcelId}</Identifier>
          <Button
            label="Open the record"
            style={{ marginTop: spacing.md }}
            onPress={() =>
              navigation.navigate("CitizenRecord", {
                parcelId: active.parcelId,
                khasra: active.khasra,
              })
            }
          />
          <Text style={styles.caveat}>
            Opening a record you do not hold will be refused by the server. The
            map shows the shape of the cadastre; it does not grant access to
            anyone else&rsquo;s record (§62).
          </Text>
        </Card>
      ) : shapes.length > 0 ? (
        <Text style={styles.hint}>
          Tap a parcel to see which khasra it is. {shapes.length} parcels mapped.
        </Text>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxl },
  header: { gap: spacing.xs },
  village: { fontSize: 20, fontWeight: "700", color: colors.navyDark },
  chips: { flexDirection: "row", gap: spacing.sm, paddingVertical: 2 },
  chip: {
    borderWidth: 1,
    borderColor: colors.sand200,
    backgroundColor: colors.white,
    borderRadius: radius.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  chipOn: { borderColor: colors.burnt, backgroundColor: colors.cream },
  chipLabel: { fontSize: 13, color: colors.sand700 },
  chipLabelOn: { color: colors.burnt, fontWeight: "600" },
  mapCard: { alignItems: "center", padding: spacing.md },
  canvas: { backgroundColor: colors.sand50, borderRadius: radius.card },
  canvasPlaceholder: {
    width: CANVAS,
    height: CANVAS,
    alignItems: "center",
    justifyContent: "center",
  },
  khasra: { fontSize: 18, fontWeight: "600", color: colors.navyDark },
  caveat: { fontSize: 12, color: colors.sand500, lineHeight: 17, marginTop: spacing.sm },
  hint: { fontSize: 13, color: colors.sand500, textAlign: "center" },
});
