import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    children: [
      { path: '',        redirect: '/map' },
      { path: 'map',     component: () => import('../views/MapView.vue') },
      { path: 'users',   component: () => import('../views/UsersView.vue') },
      { path: 'groups',  component: () => import('../views/GroupsView.vue') },
      { path: 'devices', component: () => import('../views/DevicesView.vue') },
      { path: 'export',  component: () => import('../views/ExportView.vue') },
      { path: 'selectofflinemap', component: () => import('../views/SelectOfflineMap.vue') },
      { path: 'settings', component: () => import('../views/SettingsView.vue'), meta: { adminOnly: true } },
      { path: 'about',   component: () => import('../views/AboutView.vue') },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

export async function guard(to) {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) return '/login'
  // The guard is the control; hiding the nav item is cosmetic. The API enforces the role too.
  if (to.meta.adminOnly) {
    try {
      if (!auth.user) await auth.fetchMe()
    } catch {
      return '/map'
    }
    if (auth.user?.role !== 'admin') return '/map'
  }
}

router.beforeEach(guard)

export default router
