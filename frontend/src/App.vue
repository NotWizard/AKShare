<script setup lang="ts">
import { RouterView } from 'vue-router'
import Sidebar from './components/layout/Sidebar.vue'
import RefreshBar from './components/layout/RefreshBar.vue'
</script>

<template>
  <div class="min-h-screen bg-bg">
    <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[200] focus:bg-surface focus:text-text focus:px-3 focus:py-2 focus:rounded">跳到主内容</a>
    <Sidebar />
    <main id="main" class="ml-[200px] h-screen overflow-y-auto overflow-x-hidden">
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
