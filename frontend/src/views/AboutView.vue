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
        <ul class="contact-list">
          <li v-for="c in contacts" :key="c.email" class="contact">
            <span class="contact-name">{{ c.name }}</span>
            <dl class="contact-rows">
              <dt>{{ t('about.phone') }}</dt>
              <dd>
                <a class="contact-link" :href="'tel:' + c.e164" :aria-label="t('about.callPerson', { name: c.name, phone: c.phone })">{{ c.phone }}</a>
              </dd>
              <dt>{{ t('about.email') }}</dt>
              <dd>
                <a class="contact-link" :href="'mailto:' + c.email" :aria-label="t('about.emailPerson', { name: c.name, email: c.email })">{{ c.email }}</a>
              </dd>
            </dl>
          </li>
        </ul>
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
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()

onMounted(async () => {
  if (!authStore.user) await authStore.fetchMe()
})

// Contacts as data: the visible number is formatted +359 XXX XXX XXX, tel: gets it without spaces.
const CONTACTS = [
  { name: 'Konstantin Velev', phone: '+359 877 389 417', email: 'konsvelev@gmail.com' },
  { name: 'Kiril Penev',      phone: '+359 883 545 571', email: 'k.penev@outlook.com' },
  { name: 'Kiril Iliev',      phone: '+359 889 396 793', email: 'office@hemussoftware.com' },
]
const contacts = CONTACTS.map(c => ({ ...c, e164: c.phone.replace(/\s/g, '') }))
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

.about-section { margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid var(--border); }
.about-section:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
.about-section h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 10px;
}

.contact-list { list-style: none; display: grid; gap: 16px; }
.contact { display: grid; gap: 4px; }
.contact-name { font-size: 14px; font-weight: 600; color: var(--text); }
.contact-rows {
  display: grid;
  grid-template-columns: 5.5rem 1fr;
  gap: 2px 12px;
  align-items: baseline;
}
.contact-rows dt { font-size: 13px; color: var(--text-muted); }
.contact-rows dd { min-width: 0; }
.contact-link {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 3px;
  overflow-wrap: anywhere;
  transition: text-decoration-color .15s;
}
@media (hover: hover) and (pointer: fine) { .contact-link:hover { text-decoration-color: currentColor; } }
.contact-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }
@media (prefers-reduced-motion: reduce) { .contact-link { transition: none; } }
.about-section p {
  font-size: 14px;
  color: var(--text);
  line-height: 1.6;
  white-space: pre-line;
}
.placeholder-text { color: var(--text-muted); }

</style>
