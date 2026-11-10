<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ t('devices.title') }}</h2>
      <button @click="openForm(null)">{{ t('devices.add') }}</button>
    </div>
    <p v-if="pageError" class="page-error">{{ pageError }}</p>

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
          <select v-model="form.device_type" :disabled="!!editing">
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
import { getDevices, createDevice, updateDevice, deleteDevice, reactivateDevice, permanentDeleteDevice, getUsers } from '../../../api'
import { errorText } from '../../../api/client'
import { useLocationsStore } from '../../../stores/locations'

const { t } = useI18n()
const locationsStore = useLocationsStore()

const devices   = ref([])
const users     = ref([])
const showModal = ref(false)
const editing   = ref(null)
const form      = ref({})
const formError = ref('')
const pageError = ref('')

onMounted(load)

async function load() {
  try {
    const [devs, ur] = await Promise.all([getDevices(), getUsers({ limit: 500 })])
    devices.value = devs
    users.value   = ur.items
    pageError.value = ''
  } catch (e) {
    pageError.value = errorText(e, t('devices.loadError'))
  }
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
    if (editing.value) {
      const reassigned = form.value.user_id !== editing.value.user_id
      await updateDevice(editing.value.id, form.value)
      if (reassigned) locationsStore.resetTrail(editing.value.id)
    } else {
      await createDevice(form.value)
    }
    showModal.value = false
    await load()
  } catch (e) { formError.value = errorText(e) }
}

async function deactivate(d) {
  pageError.value = ''
  if (!confirm(t('devices.confirmDeactivate', { sn: d.dev_sn }))) return
  try {
    await deleteDevice(d.id)
    locationsStore.removePosition(d.id)
    await load()
  } catch (e) { pageError.value = errorText(e) }
}

async function reactivate(d) {
  pageError.value = ''
  try {
    await reactivateDevice(d.id)
    await load()
  } catch (e) { pageError.value = errorText(e) }
}

async function remove(d) {
  pageError.value = ''
  if (!confirm(t('devices.confirmDelete', { sn: d.dev_sn }))) return
  try {
    await permanentDeleteDevice(d.id)
    locationsStore.removePosition(d.id)
    await load()
  } catch (e) { pageError.value = errorText(e) }
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
