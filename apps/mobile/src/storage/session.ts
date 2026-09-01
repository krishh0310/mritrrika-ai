/**
 * Token storage on the device.
 *
 * SecureStore, not AsyncStorage: tokens go in the keychain / Android keystore,
 * which is the whole reason §4 lists Expo SecureStore as a dependency. Field
 * phones get lost, and a token sitting in plain app storage on a lost phone is
 * a live session someone else can pick up.
 *
 * SecureStore is unavailable on web and can fail on a device whose keychain is
 * locked, so every call is guarded. The guard falls back to memory rather than
 * to nothing: swallowing the write and then reading back `null` would mean the
 * very next request goes out unauthenticated and the app bounces to sign-in on
 * a loop, which is how this read as a broken login rather than as degraded
 * storage. Memory keeps the session alive for this app run and no longer --
 * nothing unencrypted is ever written to disk, so the reason SecureStore is
 * here in the first place still holds.
 */

import * as SecureStore from "expo-secure-store";

const KEY = "mrittika.session";

export type Tokens = { accessToken: string; refreshToken: string };

/** Fallback only. Never written to disk, and gone when the app is killed. */
let memoryTokens: Tokens | null = null;

export async function readTokens(): Promise<Tokens | null> {
  try {
    const raw = await SecureStore.getItemAsync(KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed?.accessToken === "string") return parsed as Tokens;
    }
  } catch {
    // Keychain unavailable. Fall through to whatever this run holds.
  }
  return memoryTokens;
}

export async function writeTokens(tokens: Tokens): Promise<void> {
  memoryTokens = tokens;
  try {
    await SecureStore.setItemAsync(KEY, JSON.stringify(tokens));
  } catch {
    // Keychain unavailable. The session lives for this app run only.
  }
}

export async function clearTokens(): Promise<void> {
  // Cleared first: a signed-out user must not stay signed in just because
  // deleting from the keychain threw.
  memoryTokens = null;
  try {
    await SecureStore.deleteItemAsync(KEY);
  } catch {
    /* nothing to clear */
  }
}
