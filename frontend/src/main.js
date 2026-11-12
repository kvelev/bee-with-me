import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { installErrorHandlers } from './platform/errors.js'
import './style.css'
import 'ol/ol.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
installErrorHandlers(app)
app.mount('#app')
