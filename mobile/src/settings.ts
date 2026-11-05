// Engine connection settings, persisted with expo-secure-store (device keychain).
// The token is the shared engine secret — stored only here, never logged, never
// bundled as a default (rotate-on-loss, docs 06 / OD 8).

import * as SecureStore from 'expo-secure-store';

export interface EngineSettings {
  baseUrl: string;
  token: string;
}

const STORE_KEY = 'seeker.engine.v1';

export const DEFAULT_SETTINGS: EngineSettings = {
  // This deployment's node on the tailnet (joined 2026-11-05, docs 12).
  baseUrl: 'http://search-engine-2.taile24e8b.ts.net:8420',
  token: '',
};

export async function loadSettings(): Promise<EngineSettings> {
  try {
    const raw = await SecureStore.getItemAsync(STORE_KEY);
    if (!raw) {
      return {...DEFAULT_SETTINGS};
    }
    const parsed = JSON.parse(raw) as Partial<EngineSettings>;
    return {
      baseUrl: parsed.baseUrl?.trim() || DEFAULT_SETTINGS.baseUrl,
      token: parsed.token ?? '',
    };
  } catch {
    // Keychain unavailable (e.g. Expo Go edge cases) — degrade to defaults, no crash.
    return {...DEFAULT_SETTINGS};
  }
}

export async function saveSettings(settings: EngineSettings): Promise<void> {
  await SecureStore.setItemAsync(STORE_KEY, JSON.stringify(settings));
}
