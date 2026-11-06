// Seeker mobile — thin shell over the engine REST API (standing rule 2):
// search bar → POST /v1/search, source chips → filters.source_id, settings →
// keychain. No client-specific logic, no second engine implementation.

import {useCallback, useEffect, useRef, useState, type ReactNode} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  RefreshControl,
  StatusBar as RNStatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {StatusBar} from 'expo-status-bar';
import {useColorScheme} from 'react-native';
import {dark, light, spacing, radius} from './src/theme';
import {EngineSettings, loadSettings, saveSettings} from './src/settings';
import {
  EngineError,
  SearchResult,
  SourceRecord,
  listSources,
  search,
} from './src/engineApi';
import {SourceFilter} from './src/components/SourceFilter';
import {ResultRow} from './src/components/ResultRow';
import {SettingsModal} from './src/components/SettingsModal';

const TOP_K = 20;

export default function App() {
  const scheme = useColorScheme();
  const colors = scheme === 'dark' ? dark : light;
  const styles = stylesFor(colors);

  const [settings, setSettings] = useState<EngineSettings | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [error, setError] = useState<EngineError | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const lastQueryRef = useRef('');

  const refreshSources = useCallback(async (cfg: EngineSettings) => {
    try {
      setSources(await listSources(cfg.baseUrl, cfg.token));
      setError(null);
    } catch (err) {
      if (err instanceof EngineError) {
        setError(err);
      }
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const cfg = await loadSettings();
      setSettings(cfg);
      if (cfg.token) {
        await refreshSources(cfg);
      } else {
        setSettingsOpen(true); // first run — ask for the token before anything else
      }
    })();
  }, [refreshSources]);

  const runSearch = useCallback(
    async (q: string, sourceIds: ReadonlySet<string>) => {
      if (!settings || !q.trim()) {
        return;
      }
      lastQueryRef.current = q;
      setLoading(true);
      setError(null);
      const started = Date.now();
      try {
        const res = await search(settings.baseUrl, settings.token, {
          query: q.trim(),
          topK: TOP_K,
          sourceIds: [...sourceIds],
        });
        setResults(res.results);
        setElapsedMs(Date.now() - started);
      } catch (err) {
        if (err instanceof EngineError) {
          setError(err);
          setResults([]);
        }
      } finally {
        setLoading(false);
      }
    },
    [settings],
  );

  const toggleSource = useCallback(
    (sourceId: string) => {
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(sourceId)) {
          next.delete(sourceId);
        } else {
          next.add(sourceId);
        }
        if (lastQueryRef.current) {
          void runSearch(lastQueryRef.current, next);
        }
        return next;
      });
    },
    [runSearch],
  );

  const onRefresh = useCallback(async () => {
    if (!settings) {
      return;
    }
    setRefreshing(true);
    await refreshSources(settings);
    if (lastQueryRef.current) {
      await runSearch(lastQueryRef.current, selected);
    }
    setRefreshing(false);
  }, [settings, refreshSources, runSearch, selected]);

  const handleSave = useCallback(async (cfg: EngineSettings) => {
    await saveSettings(cfg);
    setSettings(cfg);
    setSettingsOpen(false);
    setSelected(new Set());
    await refreshSources(cfg);
    if (lastQueryRef.current) {
      await runSearch(lastQueryRef.current, new Set());
    }
  }, [refreshSources, runSearch]);

  const hasQuery = lastQueryRef.current.trim().length > 0;

  return (
    <SafeArea>
      <View style={styles.page}>
        <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
        <View style={styles.header}>
          <Text style={styles.brand}>Seeker</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Settings"
            onPress={() => setSettingsOpen(true)}
            hitSlop={12}>
            <Text style={styles.gear}>⚙</Text>
          </Pressable>
        </View>

        <TextInput
          style={styles.searchBar}
          value={query}
          onChangeText={setQuery}
          placeholder="Search your files…"
          placeholderTextColor={colors.muted}
          returnKeyType="search"
          autoCapitalize="none"
          autoCorrect={false}
          onSubmitEditing={() => void runSearch(query, selected)}
        />

        <SourceFilter sources={sources} selected={selected} onToggle={toggleSource} colors={colors} />

        {error != null && (
          <View style={styles.errorBanner}>
            <Text style={styles.errorText}>
              {error.code === 'NETWORK_ERROR' || error.code === 'TIMEOUT'
                ? "Can't reach the engine — check Tailscale on this device and Settings."
                : `${error.code}: ${error.message}`}
            </Text>
            <Pressable onPress={() => setSettingsOpen(true)} hitSlop={8}>
              <Text style={styles.errorAction}>Settings</Text>
            </Pressable>
          </View>
        )}

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={colors.accent} />
          </View>
        ) : results.length > 0 ? (
          <Text style={styles.count}>
            {results.length} result{results.length === 1 ? '' : 's'}
            {elapsedMs != null ? ` · ${elapsedMs} ms` : ''}
          </Text>
        ) : (
          <View style={styles.center}>
            <Text style={styles.emptyHint}>
              {error != null
                ? 'Fix the connection and search again.'
                : hasQuery
                  ? 'No results — try fewer filter sources or a vaguer phrase.'
                  : 'Search across your indexed files.'}
            </Text>
          </View>
        )}

        {results.length > 0 && (
          <FlatList
            data={results}
            keyExtractor={(item) => item.chunk_id}
            renderItem={({item}) => <ResultRow result={item} colors={colors} />}
            ItemSeparatorComponent={() => <View style={styles.separator} />}
            contentContainerStyle={styles.list}
            keyboardShouldPersistTaps="handled"
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={() => void onRefresh()}
                tintColor={colors.accent}
              />
            }
          />
        )}

        <SettingsModal
          visible={settingsOpen}
          initial={settings ?? {baseUrl: '', token: ''}}
          colors={colors}
          onClose={(saved) => {
            if (saved) {
              void handleSave(saved);
            } else {
              setSettingsOpen(false);
            }
          }}
        />
      </View>
    </SafeArea>
  );
}

function SafeArea({children}: {children: ReactNode}) {
  // RN core SafeAreaView pads iOS; Android gets the status-bar height (edge-to-edge).
  const top = Platform.OS === 'android' ? (RNStatusBar.currentHeight ?? 0) : 0;
  return <View style={{flex: 1, paddingTop: top}}>{children}</View>;
}

function stylesFor(c: (typeof light | typeof dark)) {
  return StyleSheet.create({
    page: {flex: 1, backgroundColor: c.bg, paddingHorizontal: spacing.l},
    header: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingTop: spacing.m,
      paddingBottom: spacing.s,
    },
    brand: {color: c.text, fontSize: 24, fontWeight: '800', letterSpacing: -0.5},
    gear: {color: c.muted, fontSize: 24},
    searchBar: {
      backgroundColor: c.card,
      color: c.text,
      borderRadius: radius.m,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
      paddingHorizontal: spacing.m,
      paddingVertical: 12,
      fontSize: 16,
    },
    errorBanner: {
      backgroundColor: c.card,
      borderColor: c.danger,
      borderWidth: 1,
      borderRadius: radius.s,
      padding: spacing.m,
      marginTop: spacing.s,
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: spacing.s,
    },
    errorText: {color: c.danger, fontSize: 13, flex: 1},
    errorAction: {color: c.accent, fontWeight: '600', fontSize: 13},
    center: {flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.s},
    emptyHint: {color: c.muted, fontSize: 15, textAlign: 'center', paddingHorizontal: spacing.xl},
    count: {color: c.muted, fontSize: 12, marginTop: spacing.s, marginBottom: spacing.xs},
    list: {paddingBottom: spacing.xl, gap: spacing.s, paddingTop: spacing.xs},
    separator: {height: 0},
  });
}
