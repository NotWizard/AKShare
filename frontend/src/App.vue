<script setup lang="ts">
import { RouterView } from 'vue-router'
import Sidebar from './components/layout/Sidebar.vue'
import RefreshBar from './components/layout/RefreshBar.vue'
</script>

<template>
  <div class="min-h-screen flex bg-bg">
    <Sidebar />
    <main class="flex-1 min-h-screen">
      <RefreshBar />
      <RouterView />
    </main>
  </div>
</template>
