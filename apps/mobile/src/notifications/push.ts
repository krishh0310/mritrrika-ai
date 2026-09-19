import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { api } from "../api/client";

/**
 * Register this phone for push notifications (§19).
 *
 * Best-effort by design: a refused permission, a simulator or no network must
 * never fail sign-in. Push is a convenience -- every notification is also in
 * the in-app list.
 */
export async function registerForPush(): Promise<void> {
  if (Platform.OS === "web") return;
  try {
    const { status } = await Notifications.requestPermissionsAsync();
    if (status !== "granted") return;
    const projectId = Constants.expoConfig?.extra?.eas?.projectId as string | undefined;
    const { data } = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    await api.put("/api/v1/auth/push-token", { token: data });
  } catch {
    // ponytail: silent on purpose; add reporting if push registration matters.
  }
}

/** Stop pushing to this phone. Called before the session is cleared. */
export async function unregisterPush(): Promise<void> {
  if (Platform.OS === "web") return;
  try {
    await api.put("/api/v1/auth/push-token", { token: null });
  } catch {
    // Offline sign-out still succeeds; the server just keeps a stale token.
  }
}
