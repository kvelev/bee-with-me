<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ t('nav.about') }}</h2>
    </div>

    <div class="card about-card">
      <div class="about-logo">
        <img src="../assets/asp-logo-1.png" class="about-logo-img" alt="ASP logo" />
        <h1 class="app-name">Bee With Me</h1>
        <span class="version">v1.0.0</span>
      </div>

      <div class="about-section">
        <h3>{{ t('about.description') }}</h3>
        <p>Offline people-tracking application for LoRaWAN-based rescue operations.</p>
      </div>

      <div class="about-section">
        <h3>{{ t('about.contact') }}</h3>
        <p>Konstantin Velev<br>Phone: 0877389417<br>Email: konsvelev@gmail.com</p>
        <p style="margin-top:8px">Kiril Penev</p>
      </div>

      <div class="about-section">
        <h3>{{ t('about.team') }}</h3>
        <p>ASP RESCUER TEAM<br><a href="https://rescuer.team" target="_blank" rel="noopener">https://rescuer.team</a></p>
      </div>

      <div class="about-section">
        <h3>{{ t('about.license') }}</h3>
        <p class="placeholder-text">—</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<style scoped>
.page { padding: 24px; flex: 1; }

.about-card {
  max-width: 640px;
  padding: 36px;
}

.about-logo {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}
.about-logo-img { width: 52px; height: 52px; object-fit: contain; }
.app-name   { font-size: 22px; font-weight: 700; margin: 0; }
.version    { font-size: 12px; color: var(--text-muted); margin-left: auto; }

.about-section {
  margin-bottom: 24px;
}
.about-section h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-bottom: 6px;
}
.about-section p {
  font-size: 14px;
  color: var(--text);
  line-height: 1.6;
  white-space: pre-line;
}
.placeholder-text { color: var(--text-muted); }
</style>
