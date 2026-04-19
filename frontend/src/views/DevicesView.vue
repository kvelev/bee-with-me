<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ t('devices.title') }}</h2>
      <button @click="openForm(null)">{{ t('devices.add') }}</button>
    </div>

    <div class="card">
      <table>
        <thead>
          <tr>
            <th>{{ t('devices.devSn') }}</th><th>{{ t('devices.name') }}</th>
            <th>{{ t('devices.type') }}</th><th>{{ t('devices.assignedTo') }}</th>
            <th>{{ t('devices.status') }}</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in devices" :key="d.id">
            <td><code>{{ d.dev_sn }}</code></td>
            <td>{{ d.name || '—' }}</td>
            <td><span class="badge" :class="d.device_type === 'bee' ? 'badge-bee' : 'badge-rep'">{{ d.device_type }}</span></td>
            <td>{{ d.user_name ? `${d.user_name}${d.user_rank ? ' (' + d.user_rank + ')' : ''}` : '—' }}</td>
            <td><span :class="d.is_active ? 'status-on' : 'status-off'">{{ d.is_active ? t('devices.active') : t('devices.inactive') }}</span></td>
            <td class="actions">
              <button class="secondary" @click="openForm(d)">{{ t('devices.edit') }}</button>
              <button v-if="d.is_active"  class="warning" @click="deactivate(d)">{{ t('devices.deactivate') }}</button>
              <button v-else              class="secondary" @click="reactivate(d)">{{ t('devices.reactivate') }}</button>
              <button class="danger"      @click="remove(d)">{{ t('devices.delete') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="modal-backdrop" @click.self="showModal = false">
      <div class="modal">
        <h3>{{ editing ? t('devices.form.title_edit') : t('devices.form.title_add') }}</h3>
        <div class="form-group"><label>{{ t('devices.form.devSn') }} *</label>
          <input v-model.number="form.dev_sn" type="number" :disabled="!!editing" />
        </div>
        <div class="form-group"><label>{{ t('devices.form.nameLabel') }}</label>
          <input v-model="form.name" placeholder="e.g. Unit-01" />
        </div>
        <div class="form-group"><label>{{ t('devices.form.type') }}</label>
          <select v-model="form.device_type">
            <option value="bee">RescuerBee</option>
            <option value="repeater">RescuerRepeater</option>
          </select>
        </div>
        <div class="form-group"><label>{{ t('devices.form.assignTo') }}</label>
          <select v-model="form.user_id">
            <option :value="null">{{ t('devices.form.unassigned') }}</option>
            <option v-for="u in users" :key="u.id" :value="u.id">
              {{ u.full_name }} {{ u.rank ? `(${u.rank})` : '' }}
            </option>
          </select>
        </div>
        <p v-if="formError" class="error">{{ formError }}</p>
        <div class="modal-actions">
          <button class="secondary" @click="showModal = false">{{ t('devices.form.cancel') }}</button>
          <button @click="save">{{ t('devices.form.save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getDevices, createDevice, updateDevice, deleteDevice, reactivateDevice, permanentDeleteDevice, getUsers } from '../api'

const { t } = useI18n()

const devices   = ref([])
const users     = ref([])
const showModal = ref(false)
const editing   = ref(null)
const form      = ref({})
const formError = ref('')

onMounted(load)

async function load() {
  const [devs, ur] = await Promise.all([getDevices(), getUsers({ limit: 500 })])
  devices.value = devs
  users.value   = ur.items
}

function openForm(d) {
  editing.value   = d
  formError.value = ''
  form.value = d
    ? { name: d.name, device_type: d.device_type, user_id: d.user_id }
    : { device_type: 'bee', user_id: null }
  showModal.value = true
}

async function save() {
  formError.value = ''
  try {
    if (editing.value) await updateDevice(editing.value.id, form.value)
    else               await createDevice(form.value)
    showModal.value = false
    await load()
  } catch (e) { formError.value = e }
}

async function deactivate(d) {
  if (!confirm(`Deactivate device SN:${d.dev_sn}?`)) return
  await deleteDevice(d.id)
  await load()
}

async function reactivate(d) {
  await reactivateDevice(d.id)
  await load()
}

async function remove(d) {
  if (!confirm(`Permanently delete device SN:${d.dev_sn}? This also deletes all its location history and cannot be undone.`)) return
  await permanentDeleteDevice(d.id)
  await load()
}
</script>

<style scoped>
.page    { padding: 24px; flex: 1; }
button.warning { background: rgba(234,179,8,.15); border-color: #ca8a04; color: #ca8a04; }
.actions { display: flex; gap: 8px; }
.error   { color: var(--danger); font-size: 13px; margin-bottom: 8px; }
code     { font-family: monospace; background: var(--bg-card); padding: 2px 6px; border-radius: 4px; }
.status-on  { color: var(--success); font-size: 13px; }
.status-off { color: var(--text-muted); font-size: 13px; }
.badge-bee { background: #1d4ed8; color: #fff; }
.badge-rep { background: #7c3aed; color: #fff; }
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,.6);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.modal {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 28px; width: 420px;
}
.modal h3 { margin-bottom: 20px; font-size: 16px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
</style>
