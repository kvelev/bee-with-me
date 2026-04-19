<template>
  <RouterView />
</template>

<script setup>
import { RouterView } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
if (auth.token) auth.fetchMe()
</script>
