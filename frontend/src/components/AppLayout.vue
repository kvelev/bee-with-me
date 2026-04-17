<template>
  <div class="layout">
    <nav class="sidebar">
      <div class="sidebar-brand">
        <img src="../assets/asp-logo-1.png" class="brand-logo" alt="ASP logo" />
        <span>Bee With Me</span>
      </div>

      <RouterLink to="/map"     class="nav-item"><span>🗺</span> {{ t('nav.map') }}</RouterLink>
      <RouterLink to="/users"   class="nav-item"><span>👤</span> {{ t('nav.users') }}</RouterLink>
      <RouterLink to="/groups"  class="nav-item"><span>👥</span> {{ t('nav.groups') }}</RouterLink>
      <RouterLink to="/devices" class="nav-item"><span>📡</span> {{ t('nav.devices') }}</RouterLink>
      <RouterLink to="/export"  class="nav-item"><span>📤</span> {{ t('nav.export') }}</RouterLink>

      <RouterLink to="/about" class="nav-item about-link"><span>ℹ️</span> {{ t('nav.about') }}</RouterLink>

      <div class="sidebar-footer">
        <span class="text-muted">{{ auth.user?.full_name }}</span>
        <div class="lang-row">
          <button
            v-for="loc in LOCALES" :key="loc.code"
            :class="['lang-btn', { active: currentLocale === loc.code }]"
            @click="switchLocale(loc.code)"
          >{{ loc.label }}</button>
        </div>
        <button class="secondary" @click="handleLogout">{{ t('nav.logout') }}</button>
      </div>
    </nav>

    <main class="main-content">
      <SOSBanner />
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { LOCALES, setLocale } from '../i18n'
import SOSBanner from './SOSBanner.vue'

const { t, locale } = useI18n()
const auth   = useAuthStore()
const router = useRouter()

const currentLocale = computed(() => locale.value)

function switchLocale(code) { setLocale(code) }

async function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { display: flex; height: 100vh; overflow: hidden; }

.sidebar {
  width: var(--sidebar-w); flex-shrink: 0;
  background: var(--bg-panel); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; padding: 16px 0;
}

.sidebar-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 0 20px 20px; font-size: 16px; font-weight: 700;
  border-bottom: 1px solid var(--border); margin-bottom: 12px;
}
.brand-logo { width: 28px; height: 28px; object-fit: contain; }

.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 20px; color: var(--text-muted);
  border-left: 3px solid transparent; transition: all .15s;
}
.nav-item:hover, .nav-item.router-link-active {
  color: var(--text); background: var(--bg-card);
  border-left-color: var(--accent);
}

.sidebar-footer {
  margin-top: auto; padding: 16px 20px;
  border-top: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 8px;
}
.text-muted { font-size: 13px; color: var(--text-muted); }

.lang-row   { display: flex; gap: 6px; }
.lang-btn {
  flex: 1; padding: 5px; font-size: 12px; font-weight: 700;
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text-muted);
}
.lang-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.main-content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
</style>
