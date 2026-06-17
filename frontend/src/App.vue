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
      <RouterView v-slot="{ Component }">
        <Transition name="fade" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<style>
.fade-enter-active, .fade-leave-active { transition: opacity 0.18s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
