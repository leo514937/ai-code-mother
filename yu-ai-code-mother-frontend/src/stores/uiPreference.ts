import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark'
export type UiMode = 'coding' | 'learning'

const THEME_STORAGE_KEY = 'ai-code-mother-theme'
const UI_MODE_STORAGE_KEY = 'ai-code-mother-ui-mode'

const applyDocumentPreferences = (themeMode: ThemeMode, uiMode: UiMode) => {
  if (typeof document === 'undefined') {
    return
  }

  const root = document.documentElement
  root.dataset.theme = themeMode
  root.dataset.uiMode = uiMode
  root.style.colorScheme = themeMode
}

const getSystemTheme = (): ThemeMode => {
  if (typeof window === 'undefined') {
    return 'light'
  }

  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const useUiPreferenceStore = defineStore('uiPreference', () => {
  const themeMode = ref<ThemeMode>('light')
  const uiMode = ref<UiMode>('coding')
  const isInitialized = ref(false)

  const initPreferences = () => {
    if (isInitialized.value || typeof window === 'undefined') {
      return
    }

    const storedThemeMode = window.localStorage.getItem(THEME_STORAGE_KEY)
    const storedUiMode = window.localStorage.getItem(UI_MODE_STORAGE_KEY)

    themeMode.value = storedThemeMode === 'dark' ? 'dark' : storedThemeMode === 'light' ? 'light' : getSystemTheme()
    uiMode.value = storedUiMode === 'learning' ? 'learning' : 'coding'

    applyDocumentPreferences(themeMode.value, uiMode.value)
    isInitialized.value = true
  }

  const setThemeMode = (nextThemeMode: ThemeMode) => {
    themeMode.value = nextThemeMode
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_STORAGE_KEY, nextThemeMode)
    }
    applyDocumentPreferences(themeMode.value, uiMode.value)
    isInitialized.value = true
  }

  const toggleThemeMode = () => {
    setThemeMode(themeMode.value === 'dark' ? 'light' : 'dark')
  }

  const setUiMode = (nextUiMode: UiMode) => {
    uiMode.value = nextUiMode
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(UI_MODE_STORAGE_KEY, nextUiMode)
    }
    applyDocumentPreferences(themeMode.value, uiMode.value)
    isInitialized.value = true
  }

  return {
    themeMode,
    uiMode,
    isInitialized,
    initPreferences,
    setThemeMode,
    toggleThemeMode,
    setUiMode,
  }
})
