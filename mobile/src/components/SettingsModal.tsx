// Settings modal — engine URL + bearer token, stored in the device keychain.
// "Test connection" exercises GET /v1/sources: proves reachability AND token
// validity in one call (health alone is anonymous).

import {useState} from 'react';
import {Modal, StyleSheet, Text, TextInput, Pressable, View, ActivityIndicator} from 'react-native';
import {ThemeColors, spacing, radius} from '../theme';
import {EngineSettings} from '../settings';
import {EngineError, listSources} from '../engineApi';

interface Props {
  visible: boolean;
  initial: EngineSettings;
  colors: ThemeColors;
  onClose: (saved: EngineSettings | null) => void;
}

export function SettingsModal({visible, initial, colors, onClose}: Props) {
  const styles = stylesFor(colors);
  const [url, setUrl] = useState(initial.baseUrl);
  const [token, setToken] = useState(initial.token);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const draft = (): EngineSettings => ({
    baseUrl: url.trim().replace(/\/+$/, ''),
    token: token.trim(),
  });

  const test = async () => {
    setBusy(true);
    setTestResult(null);
    try {
      const cfg = draft();
      const sources = await listSources(cfg.baseUrl, cfg.token);
      setTestResult(`✓ engine reachable — ${sources.length} source${sources.length === 1 ? '' : 's'}`);
    } catch (err) {
      const msg =
        err instanceof EngineError
          ? err.code === 'UNAUTHORIZED'
            ? '✗ reached engine, token rejected'
            : err.code === 'NETWORK_ERROR' || err.code === 'TIMEOUT'
              ? '✗ cannot reach engine (Tailscale on?)'
              : `✗ ${err.message}`
          : '✗ unexpected error';
      setTestResult(msg);
    } finally {
      setBusy(false);
    }
  };

  const save = () => {
    const cfg = draft();
    if (!cfg.baseUrl) {
      setTestResult('✗ engine URL required');
      return;
    }
    onClose(cfg);
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={() => onClose(null)}>
      <View style={styles.page}>
        <Text style={styles.heading}>Engine connection</Text>
        <Text style={styles.label}>Engine URL (Tailnet)</Text>
        <TextInput
          style={styles.input}
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="http://search-engine…ts.net:8420"
          placeholderTextColor={colors.muted}
        />
        <Text style={styles.label}>Bearer token</Text>
        <TextInput
          style={styles.input}
          value={token}
          onChangeText={setToken}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          placeholder="SEEKER_API_TOKEN"
          placeholderTextColor={colors.muted}
        />
        {testResult != null && <Text style={styles.testResult}>{testResult}</Text>}
        <View style={styles.buttons}>
          <Pressable style={[styles.button, styles.secondary]} onPress={() => onClose(null)}>
            <Text style={styles.secondaryText}>Cancel</Text>
          </Pressable>
          <Pressable style={[styles.button, styles.ghost]} onPress={() => void test()} disabled={busy}>
            {busy ? <ActivityIndicator color={colors.accent} /> : <Text style={styles.ghostText}>Test</Text>}
          </Pressable>
          <Pressable style={[styles.button, styles.primary]} onPress={save}>
            <Text style={styles.primaryText}>Save</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const stylesFor = (c: ThemeColors) =>
  StyleSheet.create({
    page: {flex: 1, backgroundColor: c.bg, padding: spacing.l, paddingTop: spacing.xl},
    heading: {color: c.text, fontSize: 22, fontWeight: '700', marginBottom: spacing.l},
    label: {color: c.muted, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: spacing.m, marginBottom: spacing.xs},
    input: {
      backgroundColor: c.card,
      color: c.text,
      borderRadius: radius.s,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
      paddingHorizontal: spacing.m,
      paddingVertical: 10,
      fontSize: 15,
    },
    testResult: {color: c.text, marginTop: spacing.m, fontSize: 13},
    buttons: {flexDirection: 'row', gap: spacing.s, marginTop: spacing.xl},
    button: {
      borderRadius: radius.s,
      paddingVertical: 12,
      paddingHorizontal: spacing.l,
      alignItems: 'center',
      justifyContent: 'center',
    },
    primary: {backgroundColor: c.accent, flex: 1},
    primaryText: {color: '#ffffff', fontWeight: '600', fontSize: 15},
    secondary: {backgroundColor: c.chipBg},
    secondaryText: {color: c.text, fontSize: 15},
    ghost: {borderWidth: 1, borderColor: c.border, backgroundColor: c.card},
    ghostText: {color: c.accent, fontWeight: '600', fontSize: 15},
  });
