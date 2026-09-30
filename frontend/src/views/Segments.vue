<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const saving = ref<number | null>(null)
const error = ref('')
const ok = ref('')

async function load() {
  rows.value = ((await api('/segments')) as any[]).map(r => ({
    ...r, _orig: { start_emergency_m: r.start_emergency_m, end_emergency_m: r.end_emergency_m },
  }))
}
onMounted(load)

async function save(r: any) {
  error.value = ''; ok.value = ''
  const start_emergency_m = Number(r.start_emergency_m)
  const end_emergency_m = Number(r.end_emergency_m)
  if (!Number.isFinite(start_emergency_m) || !Number.isFinite(end_emergency_m)) {
    error.value = '应急米数必须是数字'; return
  }
  // 前端先拦一道；后端整单拒绝时再回退，保证页面停在改前
  if (start_emergency_m < 0 || end_emergency_m < 0
      || start_emergency_m + end_emergency_m >= r.width_m) {
    error.value = `非法值：不得为负，且两端之和必须小于街宽 ${r.width_m} m，已停在改前`
    r.start_emergency_m = r._orig.start_emergency_m
    r.end_emergency_m = r._orig.end_emergency_m
    return
  }
  saving.value = r.id
  try {
    const saved = await api(`/segments/${r.id}/emergency`, {
      method: 'PUT',
      body: JSON.stringify({ start_emergency_m, end_emergency_m }),
    })
    Object.assign(r, saved); r._orig = { ...saved }
    ok.value = `${r.name} 应急带已登记：起点 ${saved.start_emergency_m} m / 终点 ${saved.end_emergency_m} m，刷新后仍在`
  } catch (e: any) {
    // 整单拒绝：页上回退改前值，禁止半成功
    r.start_emergency_m = r._orig.start_emergency_m
    r.end_emergency_m = r._orig.end_emergency_m
    let msg = e?.message || '保存被拒绝'
    try { msg = JSON.parse(msg).detail || msg } catch {}
    error.value = `已停在改前：${msg}`
  } finally {
    saving.value = null
  }
}
</script>
<template>
  <h1>街段</h1>
  <p class="sub">沿街可用宽度（米）· 两端应急带内不得出现摊位起止，可用开间从带内侧算起</p>
  <p v-if="error" class="ss-error">{{ error }}</p>
  <p v-if="ok" class="ss-ok">{{ ok }}</p>
  <div class="card">
    <table>
      <thead><tr><th>街段</th><th>宽度(m)</th><th>起点应急(m)</th><th>终点应急(m)</th><th>集日ID</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.name }}</td>
          <td>{{ r.width_m }}</td>
          <td><input v-model.number="r.start_emergency_m" type="number" min="0" step="0.1" style="width:6rem"></td>
          <td><input v-model.number="r.end_emergency_m" type="number" min="0" step="0.1" style="width:6rem"></td>
          <td>{{ r.market_day_id }}</td>
          <td><button class="btn" :disabled="saving === r.id" @click="save(r)">登记</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
