import type { GlobalThemeOverrides } from 'naive-ui'

export const v26ThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#5256d4',
    primaryColorHover: '#4347c4',
    primaryColorPressed: '#3a3eb8',
    primaryColorSuppl: '#5256d4',
    bodyColor: '#f7f8fa',
    cardColor: '#ffffff',
    modalColor: '#ffffff',
    popoverColor: '#ffffff',
    tableColor: '#ffffff',
    inputColor: '#f7f8fa',
    actionColor: '#f1f3f7',
    textColorBase: '#232735',
    textColor1: '#232735',
    textColor2: '#6d7384',
    textColor3: '#9aa0b0',
    dividerColor: '#e8eaf0',
    borderColor: '#e8eaf0',
    hoverColor: 'rgba(82, 86, 212, 0.06)',
    borderRadius: '12px',
    borderRadiusSmall: '9px',
    fontSize: '14px',
    fontSizeMedium: '14px',
    heightMedium: '40px',
    fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
    fontFamilyMono: "'JetBrains Mono', ui-monospace, monospace",
    successColor: '#0f7a5a',
    warningColor: '#b45309',
    errorColor: '#d33b3b',
    infoColor: '#0b74b8',
  },
  Layout: {
    color: '#f7f8fa',
    siderColor: '#ffffff',
    headerColor: '#f7f8fa',
  },
  Menu: {
    itemTextColorActive: '#5256d4',
    itemTextColorActiveHover: '#5256d4',
    itemColorActive: '#ecedfb',
    itemColorActiveHover: '#ecedfb',
  },
  Button: {
    textColorPrimary: '#ffffff',
    colorPrimary: '#5256d4',
    colorHoverPrimary: '#4347c4',
    colorPressedPrimary: '#3a3eb8',
    borderRadiusMedium: '12px',
  },
  Input: {
    color: '#f7f8fa',
    colorFocus: '#ffffff',
    border: '1px solid #dde0e8',
    borderHover: '1px solid #5256d4',
    borderFocus: '1px solid #5256d4',
    placeholderColor: '#9aa0b0',
    caretColor: '#5256d4',
    borderRadius: '11px',
  },
  Card: {
    color: '#ffffff',
    borderColor: '#e8eaf0',
    borderRadius: '18px',
  },
  Modal: {
    color: '#ffffff',
    borderRadius: '18px',
  },
  Tag: {
    borderRadius: '999px',
  },
  Tabs: {
    tabTextColorActiveLine: '#5256d4',
    tabTextColorHoverLine: '#232735',
    barColor: '#5256d4',
  },
}

export function getThemeOverrides(): GlobalThemeOverrides {
  return v26ThemeOverrides
}

// Legacy exports for tests
export const lightThemeOverrides = v26ThemeOverrides
export const darkThemeOverrides = v26ThemeOverrides
