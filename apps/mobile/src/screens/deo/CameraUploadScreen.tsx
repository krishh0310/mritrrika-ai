import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as ImageManipulator from "expo-image-manipulator";
import { useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import type { FieldStackParams } from "../../navigation";
import { Button, ErrorText } from "../../components/ui";
import { colors, spacing } from "../../theme";

/**
 * §59 CameraUpload — photograph a record in the field.
 *
 * The capture is compressed here, on the device, before it is queued (§60).
 * A 12-megapixel phone photo is ~6MB; over a village 2G tether that is minutes
 * per page. Resizing to 2000px on the long edge keeps enough resolution for
 * OCR — the §22 quality gate will reject it if it does not — while cutting the
 * upload to a few hundred kilobytes.
 */
const MAX_EDGE = 2000;
const JPEG_QUALITY = 0.75;

export function CameraUploadScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<FieldStackParams>>();
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!permission) return <View style={styles.root} />;

  if (!permission.granted) {
    return (
      <View style={styles.permission}>
        <Text style={styles.permissionTitle}>Camera access is needed</Text>
        <Text style={styles.permissionBody}>
          Mrittika uses the camera to photograph land records. Nothing is
          uploaded until you confirm the details on the next screen.
        </Text>
        <Button label="Allow camera" onPress={() => void requestPermission()} />
      </View>
    );
  }

  async function capture() {
    setBusy(true);
    setError(null);
    try {
      const photo = await camera.current?.takePictureAsync({ quality: 1 });
      if (!photo) throw new Error("The camera returned nothing");

      const longEdge = Math.max(photo.width, photo.height);
      const resized = await ImageManipulator.manipulateAsync(
        photo.uri,
        longEdge > MAX_EDGE
          ? [
              photo.width >= photo.height
                ? { resize: { width: MAX_EDGE } }
                : { resize: { height: MAX_EDGE } },
            ]
          : [],
        { compress: JPEG_QUALITY, format: ImageManipulator.SaveFormat.JPEG },
      );

      navigation.navigate("UploadMetadata", {
        uri: resized.uri,
        fileName: `capture-${Date.now()}.jpg`,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The capture failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.root}>
      <CameraView ref={camera} style={styles.camera} facing="back">
        {/* A page-shaped guide. Framing the whole page squarely is what keeps
            the §22 skew and blur scores usable. */}
        <View style={styles.guide} pointerEvents="none" />
      </CameraView>

      <View style={styles.controls}>
        {error ? <ErrorText>{error}</ErrorText> : null}
        <Text style={styles.hint}>
          Fill the frame with the page, hold steady, and avoid shadows.
        </Text>
        <Button label="Take the photograph" onPress={capture} busy={busy} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.navyDark },
  camera: { flex: 1 },
  guide: {
    position: "absolute",
    top: "8%",
    left: "6%",
    right: "6%",
    bottom: "8%",
    borderWidth: 2,
    borderColor: colors.warm,
    borderRadius: 4,
  },
  controls: { padding: spacing.lg, gap: spacing.md, backgroundColor: colors.navyDark },
  hint: { color: colors.navyLight, fontSize: 13, textAlign: "center" },
  permission: {
    flex: 1,
    justifyContent: "center",
    gap: spacing.lg,
    padding: spacing.xl,
    backgroundColor: colors.offwhite,
  },
  permissionTitle: { fontSize: 18, fontWeight: "600", color: colors.navyDark },
  permissionBody: { fontSize: 15, color: colors.sand700, lineHeight: 22 },
});
