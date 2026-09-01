/**
 * Token storage on the device.
 *
 * SecureStore, not AsyncStorage: tokens go in the keychain / Android keystore,
 * which is the whole reason §4 lists Expo SecureStore as a dependency. Field
 * phones get lost, and a token sitting in plain app storage on a lost phone is
 * a live session someone else can pick up.
 *
 * SecureStore is unavailable on web, so every call is guarded -- a developer
 * running the Expo web target gets a signed-out app rather than a crash.
 */

import * as SecureStore from "expo-secure-store";

const KEY = "mrittika.session";

export type Tokens = { accessToken: string; refreshToken: string };

export async function readTokens(): Promise<Tokens | null> {
  try {
    const raw = await SecureStore.getItemAsync(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return typeof parsed?.accessToken === "string" ? (parsed as Tokens) : null;
  } catch {
    return null;
  }
}

export async function writeTokens(tokens: Tokens): Promise<void> {
  try {
    await SecureStore.setItemAsync(KEY, JSON.stringify(tokens));
  } catch {
    // Keychain unavailable. The session lives for this app run only.
  }
}

export async function clearTokens(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(KEY);
  } catch {
    /* nothing to clear */
  }
}
