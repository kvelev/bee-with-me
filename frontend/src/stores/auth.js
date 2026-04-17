import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as apiLogin, getMe } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user  = ref(null)

  async function login(username, password) {
    const res = await apiLogin(username, password)
    token.value = res.access_token
    localStorage.setItem('token', res.access_token)
    await fetchMe()
  }

  async function fetchMe() {
    user.value = await getMe()
  }

  function logout() {
    token.value = ''
    user.value  = null
    localStorage.removeItem('token')
  }

  return { token, user, login, fetchMe, logout }
})
