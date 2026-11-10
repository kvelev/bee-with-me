import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { MODULES } from '../modules/index.js'
import { checkModules, collectRoutes, corePathsOf } from '../platform/registry.js'

const coreRoutes = [
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    children: [
      { path: '',        redirect: '/map' },
      { path: 'map',     component: () => import('../views/MapView.vue') },
      { path: 'export',  component: () => import('../views/ExportView.vue') },
      { path: 'selectofflinemap', component: () => import('../views/SelectOfflineMap.vue') },
      { path: 'about',   component: () => import('../views/AboutView.vue') },
    ],
  },
]

// A bad module list stops the app at start-up: a module route may not be public, redirect, nest routes or take a
// core path, and the router must not quietly serve something the guard was never meant to see.
const problems = checkModules(MODULES, corePathsOf(coreRoutes))
if (problems.length) throw new Error(`Invalid frontend modules:\n${problems.join('\n')}`)

// Module routes are mounted under the layout, after the core children.
const routes = coreRoutes.map((r) => (r.path === '/'
  ? { ...r, children: [...r.children, ...collectRoutes(MODULES)] }
  : r))

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
