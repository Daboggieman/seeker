// Design tokens — light/dark, read once per theme. Utilitarian: ink on paper,
// one accent, generous touch targets, muted metadata.

import {Platform} from 'react-native';

export interface ThemeColors {
  bg: string;
  card: string;
  border: string;
  text: string;
  muted: string;
  accent: string;
  accentSoft: string;
  danger: string;
  chipBg: string;
}

export const light: ThemeColors = {
  bg: '#f6f6f7',
  card: '#ffffff',
  border: '#e4e4e8',
  text: '#14161a',
  muted: '#6b7280',
  accent: '#4f46e5',
  accentSoft: '#eef0ff',
  danger: '#b91c1c',
  chipBg: '#ececf0',
};

export const dark: ThemeColors = {
  bg: '#0b0d10',
  card: '#151920',
  border: '#232a33',
  text: '#e8ebf0',
  muted: '#8b93a1',
  accent: '#818cf8',
  accentSoft: '#1e2233',
  danger: '#f87171',
  chipBg: '#1d232c',
};

export const monoFont = Platform.select({ios: 'Menlo', default: 'monospace'});

export const spacing = {xs: 4, s: 8, m: 12, l: 16, xl: 24} as const;

export const radius = {s: 8, m: 12} as const;
