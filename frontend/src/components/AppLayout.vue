<template>
  <div class="layout">
    <nav class="sidebar">
      <div class="sidebar-brand">
        <img :src="logoUrl" class="brand-logo" alt="ASP logo" />
        <span>Bee With Me</span>
      </div>

      <RouterLink
        v-for="item in visibleNav" :key="item.to"
        :to="item.to" class="nav-item"
      ><span>{{ item.icon }}</span> {{ t(item.labelKey) }}</RouterLink>

      <div class="sidebar-footer">
        <span class="text-muted">{{ auth.user?.full_name }}</span>
        <div class="lang-row">
          <button
            v-for="loc in LOCALES" :key="loc.code"
            :class="['lang-btn', { active: currentLocale === loc.code }]"
            @click="switchLocale(loc.code)"
          >{{ loc.label }}</button>
        </div>
      </div>
    </nav>

    <main class="main-content">
      <BannerStack :banners="banners" />
      <RouterView v-slot="{ Component }">
        <KeepAlive include="MapView">
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { LOCALES, setLocale } from '../i18n'
import BannerStack from '../platform/map-shell/BannerStack.vue'
import { collectBanners } from '../platform/map-shell/contributions.js'
import { LEGACY_BANNERS } from './legacyBanners.js'
import { MODULES } from '../modules/index.js'
import { useFireStore } from '../stores/fire'
import { NAV_ITEMS } from '../nav-config.js'
import logoUrl from '../assets/asp-logo-1.png'

const { t, locale } = useI18n()
const auth   = useAuthStore()
const fire   = useFireStore()

// Alarm banners come from the modules' contributions plus the legacy list, sorted by priority (SOS first).
const banners = collectBanners(MODULES, LEGACY_BANNERS)

const currentLocale = computed(() => locale.value)
// Cosmetic only: the router guard is what keeps non-admins off admin routes.
const visibleNav = computed(() =>
  NAV_ITEMS.filter(item => !item.adminOnly || auth.user?.role === 'admin'))

function switchLocale(code) { setLocale(code) }

// Open fire alarms must be on screen on every page, so they load with the layout (not with the map).
// A failure shows as a notice in the banner (alertsFailed); the 45 s resync retries it.
onMounted(() => { fire.fetchOpenAlerts().catch(() => { /* alertsFailed drives the notice */ }) })
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
