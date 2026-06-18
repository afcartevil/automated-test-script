<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { setApiKey, hasApiKey } from "@/api/client";
import { fetchAuthStatus, loginWithPassword } from "@/api/auth";

const { t } = useI18n();
const router = useRouter();

// Read token saved by main.ts (before router strips URL params)
const urlToken = (window as any).__LOGIN_TOKEN__ || "";

const token = ref(urlToken);
const username = ref("");
const password = ref("");
const loading = ref(false);
const errorMsg = ref("");

// Login method: 'token' or 'password'
const loginMethod = ref<"token" | "password">("token");
const hasPasswordLogin = ref(false);

// If already has a key, try to go to main page
if (hasApiKey()) {
  router.replace("/tahp/dashboard");
}

onMounted(async () => {
  try {
    const status = await fetchAuthStatus();
    hasPasswordLogin.value = status.hasPasswordLogin;
    if (status.hasPasswordLogin && !urlToken) {
      loginMethod.value = "password";
    }
  } catch {
    // Fallback to token-only
  }
});

async function handleLogin() {
  if (loginMethod.value === "token") {
    await handleTokenLogin();
  } else {
    await handlePasswordLogin();
  }
}

async function handleTokenLogin() {
  const key = token.value.trim();
  if (!key) {
    errorMsg.value = t("login.tokenRequired");
    return;
  }

  loading.value = true;
  errorMsg.value = "";

  try {
    const res = await fetch("/api/hermes/sessions", {
      headers: { Authorization: `Bearer ${key}` },
    });

    if (res.status === 401) {
      errorMsg.value = t("login.invalidToken");
      loading.value = false;
      return;
    }

    if (res.status === 429 || res.status === 503) {
      errorMsg.value = t("login.tooManyAttempts");
      loading.value = false;
      return;
    }

    setApiKey(key);
    router.replace("/tahp/dashboard");
  } catch {
    errorMsg.value = t("login.connectionFailed");
  } finally {
    loading.value = false;
  }
}

async function handlePasswordLogin() {
  if (!username.value.trim() || !password.value) {
    errorMsg.value = t("login.credentialsRequired");
    return;
  }

  loading.value = true;
  errorMsg.value = "";

  try {
    const sessionToken = await loginWithPassword(username.value.trim(), password.value);
    setApiKey(sessionToken);
    router.replace("/tahp/dashboard");
  } catch (err: any) {
    if (err.status === 429 || err.status === 503) {
      errorMsg.value = t("login.tooManyAttempts");
    } else {
      errorMsg.value = err.message || t("login.invalidCredentials");
    }
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-view">
    <div class="ea-card login-card">
      <div class="login-logo">
        <img src="/logo.png" alt="EasyAdapter" width="72" height="72" />
      </div>
      <h1 class="login-title">{{ t("login.title") }}</h1>
      <p class="login-desc">{{ t("login.description") }}</p>

      <div v-if="hasPasswordLogin" class="login-method-toggle">
        <button
          type="button"
          class="toggle-btn"
          :class="{ active: loginMethod === 'password' }"
          @click="loginMethod = 'password'"
        >{{ t("login.passwordLogin") }}</button>
        <button
          type="button"
          class="toggle-btn"
          :class="{ active: loginMethod === 'token' }"
          @click="loginMethod = 'token'"
        >{{ t("login.tokenLogin") }}</button>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <template v-if="loginMethod === 'token'">
          <div class="ea-field ea-mb0">
            <label>{{ t("login.tokenLogin") }}</label>
            <input
              v-model="token"
              type="password"
              class="login-input"
              :placeholder="t('login.placeholder')"
              autofocus
            />
          </div>
        </template>

        <template v-if="loginMethod === 'password'">
          <div class="ea-field ea-mb0">
            <label>{{ t("login.usernamePlaceholder") }}</label>
            <input
              v-model="username"
              type="text"
              class="login-input"
              :placeholder="t('login.usernamePlaceholder')"
              autofocus
            />
          </div>
          <div class="ea-field ea-mb0">
            <label>{{ t("login.passwordPlaceholder") }}</label>
            <input
              v-model="password"
              type="password"
              class="login-input"
              :placeholder="t('login.passwordPlaceholder')"
              @keyup.enter="handleLogin"
            />
          </div>
        </template>

        <div v-if="errorMsg" class="login-error">{{ errorMsg }}</div>
        <button type="submit" class="ea-btn-primary login-btn" :disabled="loading">
          {{ loading ? "..." : t("login.submit") }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped lang="scss">
.login-view {
  height: calc(100 * var(--vh));
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  padding: 24px;
}

.login-card {
  width: 440px;
  max-width: 100%;
  text-align: center;
  padding: 48px 40px;
}

.login-logo {
  margin-bottom: 20px;
}

.login-title {
  font-size: 26px;
  font-weight: 800;
  color: var(--head);
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}

.login-desc {
  font-size: 14px;
  color: var(--muted);
  margin: 0 0 28px;
  line-height: 1.6;
}

.login-method-toggle {
  display: flex;
  margin-bottom: 20px;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg);

  .toggle-btn {
    flex: 1;
    padding: 10px;
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.18s;

    &.active {
      background: var(--accent-soft);
      color: var(--accent);
    }

    &:not(.active):hover {
      color: var(--text);
    }
  }
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  text-align: left;
}

.login-input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  font-size: 14px;
  color: var(--text);
  background: var(--bg);
  outline: none;
  transition: border-color 0.18s;
  box-sizing: border-box;

  &::placeholder {
    color: var(--muted);
  }

  &:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(82, 86, 212, 0.12);
  }
}

.login-error {
  font-size: 13px;
  color: var(--error);
}

.login-btn {
  width: 100%;
  justify-content: center;
  margin-top: 4px;
}
</style>
