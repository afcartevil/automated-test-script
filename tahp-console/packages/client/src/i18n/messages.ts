import en from './locales/en'
import zh from './locales/zh'

export type LocaleMessages = Record<string, any>

export const supportedLocales = ['en', 'zh'] as const
export type SupportedLocale = (typeof supportedLocales)[number]

function isPlainObject(value: unknown): value is LocaleMessages {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function mergeMessagesWithFallback(
  fallback: LocaleMessages,
  locale: LocaleMessages,
): LocaleMessages {
  const merged: LocaleMessages = { ...fallback }

  for (const [key, value] of Object.entries(locale)) {
    const fallbackValue = fallback[key]
    merged[key] = isPlainObject(fallbackValue) && isPlainObject(value)
      ? mergeMessagesWithFallback(fallbackValue, value)
      : value
  }

  return merged
}

const rawMessages: Record<string, LocaleMessages> = { en, zh }

export const messages: Record<string, LocaleMessages> = {}
for (const [locale, msg] of Object.entries(rawMessages)) {
  messages[locale] = locale === 'en' ? msg : mergeMessagesWithFallback(en, msg)
}

export { en }
