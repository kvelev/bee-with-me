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
      { path: 'about',   component: () => import('../views/AboutView.vue') },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) return '/login'
})

export default router
