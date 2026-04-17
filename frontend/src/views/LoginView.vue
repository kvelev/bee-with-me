<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="handleLogin">
      <div class="login-title">
        <img src="../assets/asp-logo-1.png" class="login-logo" alt="ASP logo" />
        <h1>{{ t('login.title') }}</h1>
      </div>

      <div class="lang-row">
        <button
          v-for="loc in LOCALES" :key="loc.code" type="button"
          :class="['lang-btn', { active: currentLocale === loc.code }]"
          @click="switchLocale(loc.code)"
        >{{ loc.label }}</button>
      </div>

      <div class="form-group">
        <label>{{ t('login.username') }}</label>
        <input v-model="username" type="text" autocomplete="username" required />
      </div>
      <div class="form-group">
        <label>{{ t('login.password') }}</label>
        <input v-model="password" type="password" autocomplete="current-password" required />
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <button type="submit" :disabled="loading" style="width:100%">
        {{ loading ? t('login.loading') : t('login.submit') }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { LOCALES, setLocale } from '../i18n'

const { t, locale } = useI18n()
const currentLocale  = computed(() => locale.value)
const username = ref('')
const password = ref('')
const error    = ref('')
const loading  = ref(false)

const auth   = useAuthStore()
const router = useRouter()

function switchLocale(code) { setLocale(code) }

async function handleLogin() {
  error.value   = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push('/map')
  } catch (e) {
    error.value = t('login.error')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh; display: flex;
  align-items: center; justify-content: center;
  background: var(--bg);
}
.login-card {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 40px; width: 380px;
}
.login-title {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 20px;
}
.login-logo { width: 48px; height: 48px; object-fit: contain; }
h1 { font-size: 20px; font-weight: 700; }
.error { color: var(--danger); font-size: 13px; margin-bottom: 12px; }
.lang-row { display: flex; gap: 6px; margin-bottom: 20px; }
.lang-btn {
  flex: 1; padding: 6px; font-size: 12px; font-weight: 700;
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text-muted);
  border-radius: 6px; cursor: pointer;
}
.lang-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>
