import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import HomeView from './views/HomeView.vue'
import AnalysisView from './views/AnalysisView.vue'
import CrashAnalysisView from './views/CrashAnalysisView.vue'
import DashboardView from './views/DashboardView.vue'
import PatchDatabaseView from './views/PatchDatabaseView.vue'
import PatchDetailView from './views/PatchDetailView.vue'
import SettingsView from './views/SettingsView.vue'
import UpgradeView from './views/UpgradeView.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory('/app/'),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/dashboard', name: 'dashboard', component: DashboardView },
    { path: '/analysis', name: 'analysis', component: AnalysisView },
    { path: '/patches', name: 'patches', component: PatchDatabaseView },
    { path: '/patches/:sha', name: 'patch-detail', component: PatchDetailView },
    { path: '/upgrade', name: 'upgrade', component: UpgradeView },
    { path: '/crash', name: 'crash', component: CrashAnalysisView },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})

createApp(App).use(createPinia()).use(router).mount('#app')
