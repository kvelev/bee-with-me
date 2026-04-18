<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ t('users.title') }}</h2>
      <button @click="openForm(null)">{{ t('users.add') }}</button>
    </div>
    <p v-if="pageError" class="page-error">{{ pageError }}</p>

    <div class="card">
      <table>
        <thead>
          <tr>
            <th>{{ t('users.photo') }}</th><th>{{ t('users.name') }}</th>
            <th>{{ t('users.rank') }}</th><th>{{ t('users.blood') }}</th>
            <th>{{ t('users.form.phone') }}</th>
            <th>{{ t('users.groups') }}</th><th>{{ t('users.role') }}</th>
            <th>{{ t('users.status') }}</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <img v-if="u.photo_url" :src="u.photo_url" class="avatar" />
              <div v-else class="avatar-placeholder">{{ initials(u.full_name) }}</div>
            </td>
            <td>{{ u.full_name }}</td>
            <td>{{ u.rank || '—' }}</td>
            <td>
              <span v-if="u.blood_type" class="badge badge-blood">{{ u.blood_type }}</span>
              <span v-else>—</span>
            </td>
            <td>{{ u.phone || '—' }}</td>
            <td>
              <span v-for="g in u.groups" :key="g.id" class="group-chip" :style="{ background: g.color }">
                {{ g.name }}
              </span>
            </td>
            <td>{{ u.role }}</td>
            <td><span :class="u.is_active ? 'status-on' : 'status-off'">{{ u.is_active ? t('users.active') : t('users.inactive') }}</span></td>
            <td class="actions">
              <button class="secondary" @click="openForm(u)">{{ t('users.edit') }}</button>
              <button v-if="u.is_active" class="warning" @click="deactivate(u)" :title="t('users.deactivate')">⏸</button>
              <button v-else class="secondary" @click="reactivate(u)" :title="t('users.reactivate')">▶</button>
              <button class="danger"    @click="remove(u)">{{ t('users.delete') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Edit / Create modal -->
    <div v-if="showModal" class="modal-backdrop" @click.self="showModal = false">
      <div class="modal">
        <h3>{{ editing ? t('users.form.title_edit') : t('users.form.title_add') }}</h3>

        <!-- Photo upload -->
        <div class="photo-section">
          <img v-if="photoPreview || editing?.photo_url" :src="photoPreview || editing.photo_url" class="avatar-lg" />
          <div v-else class="avatar-lg-placeholder">{{ form.full_name ? initials(form.full_name) : '?' }}</div>
          <label class="upload-btn">
            {{ t('users.form.changePhoto') }}
            <input type="file" accept="image/jpeg,image/png,image/webp" @change="onPhotoSelected" hidden />
          </label>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>{{ t('users.form.firstName') }} *</label>
            <input v-model="form.first_name" required />
          </div>
          <div class="form-group">
            <label>{{ t('users.form.lastName') }} *</label>
            <input v-model="form.last_name" required />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>{{ t('users.rank') }}</label>
            <input v-model="form.rank" />
          </div>
          <div class="form-group">
            <label>{{ t('users.form.phone') }} *</label>
            <input v-model="form.phone" type="tel" required />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>{{ t('users.form.pin') }} {{ editing ? t('users.form.passHint') : '*' }}</label>
            <input v-model="form.pin" type="password" inputmode="numeric" maxlength="8" placeholder="••••" />
          </div>
          <div class="form-group">
            <label>{{ t('users.form.bloodType') }}</label>
            <select v-model="form.blood_type">
              <option :value="null">{{ t('users.form.unknown') }}</option>
              <option v-for="bt in BLOOD_TYPES" :key="bt" :value="bt">{{ bt }}</option>
            </select>
          </div>
        </div>
        <!-- App login toggle -->
        <div class="form-group toggle-row">
          <label class="toggle-label" :class="{ 'toggle-locked': editing?.username === 'admin' }">
            <input type="checkbox" v-model="hasLogin" :disabled="editing?.username === 'admin'" />
            {{ t('users.form.grantLogin') }}
          </label>
        </div>
        <div v-if="hasLogin" class="form-row">
          <div class="form-group">
            <label>{{ t('users.form.username') }} *</label>
            <input v-model="form.username" :disabled="!!editing" />
          </div>
          <div class="form-group">
            <label>{{ t('users.form.password') }} {{ editing ? t('users.form.passHint') : '*' }}</label>
            <input v-model="form.password" type="password" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>{{ t('users.form.appRole') }}</label>
            <select v-model="form.role">
              <option>viewer</option>
              <option>rescuer</option>
              <option>admin</option>
            </select>
          </div>
          <div class="form-group">
            <label>{{ t('users.form.email') }}</label>
            <input v-model="form.email" type="email" />
          </div>
        </div>
        <div class="form-group">
          <label>{{ t('users.form.notes') }}</label>
          <textarea v-model="form.notes" rows="3" />
        </div>
        <div class="form-group">
          <label>{{ t('users.form.device') }}</label>
          <select v-model="selectedDeviceId">
            <option :value="null">{{ t('users.form.noDevice') }}</option>
            <option v-for="d in allDevices" :key="d.id" :value="d.id">
              SN: {{ d.dev_sn }}{{ d.name ? ' — ' + d.name : '' }}{{ d.user_id && d.user_id !== editing?.id ? ' (' + (d.user_name || t('users.form.assigned')) + ')' : '' }}
            </option>
          </select>
        </div>

        <!-- Group memberships + leader toggle (only when editing) -->
        <div v-if="editing && editing.groups?.length" class="form-group">
          <label>{{ t('users.form.groupMemberships') }}</label>
          <div class="group-membership-list">
            <div v-for="g in editing.groups" :key="g.id" class="group-membership-row">
              <span class="membership-chip" :style="{ background: g.color }">{{ g.name }}</span>
              <button
                class="leader-btn"
                :class="{ 'leader-btn-active': g.is_leader }"
                @click="toggleLeader(g)"
                type="button"
              >
                {{ g.is_leader ? '★ ' + t('users.form.removeLeader') : '☆ ' + t('users.form.setLeader') }}
              </button>
              <button class="danger small" @click="removeFromTeam(g)" type="button">✕</button>
            </div>
          </div>
        </div>

        <p v-if="formError" class="error">{{ formError }}</p>
        <div class="modal-actions">
          <button class="secondary" @click="showModal = false">{{ t('users.form.cancel') }}</button>
          <button @click="save">{{ t('users.form.save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api/client'
import { getUsers, createUser, updateUser, deleteUser, deactivateUser, reactivateUser, setGroupLeader, removeMember, getDevices, assignDevice } from '../api'

const { t } = useI18n()
const BLOOD_TYPES = ['A+', 'A−', 'B+', 'B−', 'AB+', 'AB−', 'O+', 'O−']

const users      = ref([])
const allDevices = ref([])
const showModal  = ref(false)
const editing    = ref(null)
const formError  = ref('')
const pageError  = ref('')
const form       = ref({})
const hasLogin   = ref(false)
const photoFile  = ref(null)
const photoPreview    = ref(null)
const selectedDeviceId  = ref(null)   // device chosen in the form
const originalDeviceId  = ref(null)   // device the user had when form opened

onMounted(load)

async function load() {
  const [raw, devs] = await Promise.all([getUsers(), getDevices()])
  users.value = raw.map(u => ({
    ...u,
    groups: typeof u.groups === 'string' ? JSON.parse(u.groups) : (u.groups ?? []),
  }))
  allDevices.value = devs.filter(d => d.is_active)
}

function initials(name) {
  return name?.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?'
}

function openForm(user) {
  editing.value      = user
  formError.value    = ''
  photoFile.value    = null
  photoPreview.value = null
  hasLogin.value     = !!user?.username
  form.value = user
    ? { first_name: user.first_name, last_name: user.last_name,
        username: user.username, rank: user.rank, phone: user.phone,
        blood_type: user.blood_type, email: user.email,
        notes: user.notes, role: user.role }
    : { role: 'viewer', blood_type: null, phone: '' }
  const currentDevice = user
    ? allDevices.value.find(d => d.user_id === user.id) ?? null
    : null
  selectedDeviceId.value = currentDevice?.id ?? null
  originalDeviceId.value = currentDevice?.id ?? null
  showModal.value = true
}

watch(selectedDeviceId, (newId, oldId) => {
  if (!newId) return
  const device = allDevices.value.find(d => d.id === newId)
  const takenBy = device?.user_id && device.user_id !== editing.value?.id
  if (takenBy) {
    const name = device.user_name || t('users.form.assigned')
    if (!confirm(t('users.form.deviceTaken', { name, sn: device.dev_sn }))) {
      selectedDeviceId.value = oldId
    }
  }
})

function onPhotoSelected(e) {
  const file = e.target.files[0]
  if (!file) return
  photoFile.value = file
  photoPreview.value = URL.createObjectURL(file)
}

async function save() {
  formError.value = ''
  try {
    const payload = { ...form.value }
    if (!hasLogin.value) {
      delete payload.username
      delete payload.password
      if (editing.value?.username) payload.clear_login = true
    } else if (!payload.password) {
      delete payload.password
    }

    let savedId
    if (editing.value) {
      await updateUser(editing.value.id, payload)
      savedId = editing.value.id
    } else {
      const created = await createUser(payload)
      savedId = created.id
    }

    if (photoFile.value) {
      const fd = new FormData()
      fd.append('file', photoFile.value)
      await api.post(`/users/${savedId}/photo`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    }

    // Handle device assignment change
    if (selectedDeviceId.value !== originalDeviceId.value) {
      if (originalDeviceId.value) await assignDevice(originalDeviceId.value, null)
      if (selectedDeviceId.value) await assignDevice(selectedDeviceId.value, savedId)
    }

    showModal.value = false
    await load()
  } catch (e) {
    const msg = typeof e === 'string' ? e : (e?.message ?? String(e))
    if (showModal.value) formError.value = msg
    else pageError.value = msg
  }
}

async function toggleLeader(group) {
  try {
    await setGroupLeader(group.id, editing.value.id, !group.is_leader)
    group.is_leader = !group.is_leader
  } catch (e) {
    formError.value = typeof e === 'string' ? e : (e?.message ?? String(e))
  }
}

async function removeFromTeam(group) {
  try {
    await removeMember(group.id, editing.value.id)
    editing.value.groups = editing.value.groups.filter(g => g.id !== group.id)
  } catch (e) {
    formError.value = typeof e === 'string' ? e : (e?.message ?? String(e))
  }
}

async function deactivate(user) {
  pageError.value = ''
  if (!confirm(t('users.form.deactivate', { name: user.full_name }))) return
  try {
    await deactivateUser(user.id)
    await load()
  } catch (e) {
    pageError.value = typeof e === 'string' ? e : (e?.message ?? String(e))
  }
}

async function reactivate(user) {
  pageError.value = ''
  try {
    await reactivateUser(user.id)
    await load()
  } catch (e) {
    pageError.value = typeof e === 'string' ? e : (e?.message ?? String(e))
  }
}

async function remove(user) {
  pageError.value = ''
  if (!confirm(t('users.form.confirmDelete', { name: user.full_name }))) return
  try {
    await deleteUser(user.id)
    if (editing.value?.id === user.id) showModal.value = false
    await load()
  } catch (e) {
    pageError.value = typeof e === 'string' ? e : (e?.message ?? String(e))
  }
}
</script>

<style scoped>
.page      { padding: 24px; flex: 1; }
.page-error { color: var(--danger); background: rgba(239,68,68,.08); border: 1px solid var(--danger); border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px; }
.actions  { display: flex; gap: 8px; align-items: center; }
button.warning { background: rgba(234,179,8,.15); border-color: #ca8a04; color: #ca8a04; }
.group-chip { padding: 2px 8px; border-radius: 99px; font-size: 11px; color: #fff; margin-right: 4px; }
.status-on  { color: var(--success); font-size: 13px; }
.status-off { color: var(--text-muted); font-size: 13px; }
.error      { color: var(--danger); font-size: 13px; margin-bottom: 8px; }
.badge-blood { background: #7c3aed; color: #fff; font-weight: 700; }

.avatar {
  width: 36px; height: 36px; border-radius: 50%;
  object-fit: cover; border: 2px solid var(--border);
}
.avatar-placeholder {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--bg-card); border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: var(--text-muted);
}

.photo-section {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px;
}
.avatar-lg {
  width: 72px; height: 72px; border-radius: 50%;
  object-fit: cover; border: 2px solid var(--border);
}
.avatar-lg-placeholder {
  width: 72px; height: 72px; border-radius: 50%;
  background: var(--bg-card); border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 700; color: var(--text-muted);
}
.upload-btn {
  display: inline-block; cursor: pointer; padding: 7px 14px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 6px; font-size: 13px; color: var(--text);
  transition: opacity .15s;
}
.upload-btn:hover { opacity: .8; }

.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.group-membership-list { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.group-membership-row  { display: flex; align-items: center; gap: 8px; }
.membership-chip { padding: 2px 10px; border-radius: 99px; font-size: 12px; color: #fff; flex-shrink: 0; }
.leader-btn {
  font-size: 12px; padding: 3px 10px; border-radius: 4px;
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text-muted);
  cursor: pointer; transition: all .15s;
}
.leader-btn:hover      { color: var(--text); }
.leader-btn-active     { background: rgba(255,200,0,0.15); border-color: #ffc900; color: #ffc900; }
button.small           { padding: 2px 7px; font-size: 12px; }
.toggle-row { margin-bottom: 4px; }
.toggle-label { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; color: var(--text-muted); }
.toggle-label input { cursor: pointer; width: auto; }
.toggle-locked { opacity: .6; cursor: not-allowed; }
.toggle-locked input { cursor: not-allowed; }

.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,.6);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.modal {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 28px; width: 560px; max-height: 90vh; overflow-y: auto;
}
.modal h3 { margin-bottom: 20px; font-size: 16px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
textarea { resize: vertical; }
</style>
