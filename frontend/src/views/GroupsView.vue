<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ t('groups.title') }}</h2>
      <button @click="openForm(null)">{{ t('groups.add') }}</button>
    </div>

    <div class="card">
      <table>
        <thead><tr>
          <th>{{ t('groups.name') }}</th><th>{{ t('groups.organization') }}</th>
          <th>{{ t('groups.color') }}</th>
          <th>{{ t('groups.members') }}</th><th>{{ t('groups.description') }}</th><th></th>
        </tr></thead>
        <tbody>
          <tr v-for="g in groups" :key="g.id" @click="selectGroup(g)" class="clickable" :class="{ 'row-inactive': !g.is_active }">
            <td>{{ g.name }}</td>
            <td>{{ g.organization || '—' }}</td>
            <td><span class="color-swatch" :style="{ background: g.color }">{{ g.color }}</span></td>
            <td>{{ g.member_count }}</td>
            <td>{{ g.description || '—' }}</td>
            <td class="actions" @click.stop>
              <button class="secondary" @click="openForm(g)">{{ t('groups.edit') }}</button>
              <button v-if="g.is_active" class="warning" @click="deactivate(g)" :title="t('groups.deactivate')">⏸</button>
              <button v-else class="secondary" @click="reactivate(g)" :title="t('groups.reactivate')">▶</button>
              <button class="danger"    @click="remove(g)">{{ t('groups.delete') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Group detail / member management -->
    <div v-if="selected" class="card" style="margin-top:16px">
      <div class="page-header">
        <h3>
          <span class="color-dot" :style="{ background: selected.color }" />
          {{ selected.name }} — {{ t('groups.members') }}
        </h3>
        <button @click="openAddMember">{{ t('groups.addMember') }}</button>
      </div>
      <table>
        <thead><tr>
          <th>{{ t('groups.name') }}</th><th>{{ t('users.rank') }}</th>
          <th>{{ t('groups.leader') }}</th><th></th>
        </tr></thead>
        <tbody>
          <tr v-for="m in selected.members" :key="m.id">
            <td>{{ m.full_name }}</td>
            <td>{{ m.rank || '—' }}</td>
            <td>{{ m.is_leader ? '★' : '' }}</td>
            <td><button class="danger" @click="kickMember(m)">{{ t('groups.remove') }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Group form modal -->
    <div v-if="showForm" class="modal-backdrop" @click.self="showForm = false">
      <div class="modal">
        <h3>{{ editingGroup ? t('groups.form.title_edit') : t('groups.form.title_add') }}</h3>
        <div class="form-group"><label>{{ t('groups.form.name') }} *</label><input v-model="form.name" /></div>
        <div class="form-group"><label>{{ t('groups.form.organization') }}</label><input v-model="form.organization" /></div>
        <div class="form-group"><label>{{ t('groups.form.desc') }}</label><input v-model="form.description" /></div>
        <div class="form-group">
          <label>{{ t('groups.form.color') }}</label>
          <div class="color-row">
            <input v-model="form.color" type="color" class="color-picker" />
            <input v-model="form.color" style="flex:1" />
          </div>
        </div>
        <!-- Inline member management -->
        <div class="form-group">
          <label>{{ t('groups.members') }}</label>
          <div class="member-add-row">
            <select v-model="memberToAdd.user_id" class="member-select">
              <option value="">— {{ t('groups.form.person') }} —</option>
              <option
                v-for="u in availableUsers"
                :key="u.id" :value="u.id"
              >{{ u.full_name }}{{ u.rank ? ` (${u.rank})` : '' }}</option>
            </select>
            <label class="leader-check">
              <input type="checkbox" v-model="memberToAdd.is_leader" />
              {{ t('groups.form.isLeader') }}
            </label>
            <button type="button" class="secondary" @click="addInlineMember" :disabled="!memberToAdd.user_id">+</button>
          </div>
          <div v-if="pendingMembers.length" class="pending-member-list">
            <div v-for="(m, i) in pendingMembers" :key="m.user_id" class="pending-member-row">
              <button
                type="button"
                :class="['leader-toggle', { active: m.is_leader }]"
                @click="m.is_leader = !m.is_leader"
                :title="m.is_leader ? t('groups.form.isLeader') : t('groups.form.isLeader')"
              >★</button>
              <span class="member-name">{{ m.full_name }}{{ m.rank ? ` (${m.rank})` : '' }}</span>
              <button type="button" class="danger small" @click="removePendingMember(i)">✕</button>
            </div>
          </div>
        </div>

        <p v-if="formError" class="error">{{ formError }}</p>
        <div class="modal-actions">
          <button class="secondary" @click="showForm = false">{{ t('groups.form.cancel') }}</button>
          <button @click="save">{{ t('groups.form.save') }}</button>
        </div>
      </div>
    </div>

    <!-- Add member modal -->
    <div v-if="showAddMember" class="modal-backdrop" @click.self="showAddMember = false">
      <div class="modal">
        <h3>{{ t('groups.form.addMember', { name: selected?.name }) }}</h3>
        <div class="form-group">
          <div v-if="memberCandidates.length === 0" class="no-candidates">{{ t('groups.form.noAvailable') }}</div>
          <div v-else class="candidate-list">
            <div v-for="u in memberCandidates" :key="u.id" class="candidate-row">
              <label class="candidate-check">
                <input
                  type="checkbox"
                  v-model="candidateChecked[u.id]"
                  @change="onCandidateChange(u.id)"
                />
                {{ u.full_name }}{{ u.rank ? ` (${u.rank})` : '' }}
              </label>
              <button
                v-if="candidateChecked[u.id]"
                type="button"
                :class="['leader-toggle', { active: leaderCandidateId === u.id }]"
                @click="leaderCandidateId = leaderCandidateId === u.id ? null : u.id"
                :title="t('groups.form.isLeader')"
              >★</button>
            </div>
          </div>
        </div>
        <p v-if="memberError" class="error">{{ memberError }}</p>
        <div class="modal-actions">
          <button class="secondary" @click="showAddMember = false">{{ t('groups.form.cancel') }}</button>
          <button @click="saveMember" :disabled="!memberCandidates.some(u => candidateChecked[u.id])">{{ t('groups.addMember') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getGroups, getGroup, createGroup, updateGroup, deleteGroup,
  deactivateGroup, reactivateGroup,
  addMember, removeMember, getUsers,
} from '../api'

const { t } = useI18n()

const groups         = ref([])
const selected       = ref(null)
const allUsers       = ref([])
const showForm       = ref(false)
const showAddMember  = ref(false)
const editingGroup   = ref(null)
const form           = ref({})
const memberCandidates  = ref([])
const candidateChecked  = reactive({})   // uid -> boolean
const leaderCandidateId = ref(null)
const formError      = ref('')
const pendingMembers = ref([])   // staged for create; live for edit
const memberToAdd    = ref({ user_id: '', is_leader: false })
const memberError    = ref('')

// Users not yet in the pending list
const availableUsers = computed(() =>
  allUsers.value.filter(u => !pendingMembers.value.some(m => m.user_id === u.id))
)

onMounted(load)

async function load() {
  groups.value   = await getGroups()
  allUsers.value = await getUsers()
}

async function selectGroup(g) {
  selected.value = await getGroup(g.id)
}

async function openForm(g) {
  editingGroup.value   = g
  formError.value      = ''
  memberToAdd.value    = { user_id: '', is_leader: false }
  form.value = g
    ? { name: g.name, description: g.description, organization: g.organization, color: g.color }
    : { color: '#3388ff' }

  if (g) {
    const detail = await getGroup(g.id)
    pendingMembers.value = detail.members.map(m => ({
      user_id: m.id, full_name: m.full_name, rank: m.rank, is_leader: m.is_leader,
    }))
  } else {
    pendingMembers.value = []
  }
  showForm.value = true
}

function addInlineMember() {
  const user = allUsers.value.find(u => u.id === memberToAdd.value.user_id)
  if (!user) return
  pendingMembers.value.push({
    user_id: user.id, full_name: user.full_name, rank: user.rank,
    is_leader: memberToAdd.value.is_leader,
  })
  memberToAdd.value = { user_id: '', is_leader: false }
}

function removePendingMember(idx) {
  pendingMembers.value.splice(idx, 1)
}

async function save() {
  formError.value = ''
  try {
    if (editingGroup.value) {
      await updateGroup(editingGroup.value.id, form.value)
      // Sync members: remove all then re-add from pendingMembers
      const detail = await getGroup(editingGroup.value.id)
      await Promise.all(detail.members.map(m => removeMember(editingGroup.value.id, m.id)))
      await Promise.all(pendingMembers.value.map(m =>
        addMember(editingGroup.value.id, { user_id: m.user_id, is_leader: m.is_leader })
      ))
    } else {
      const created = await createGroup(form.value)
      await Promise.all(pendingMembers.value.map(m =>
        addMember(created.id, { user_id: m.user_id, is_leader: m.is_leader })
      ))
    }
    showForm.value = false
    await load()
    if (selected.value) selected.value = await getGroup(selected.value.id)
  } catch (e) { formError.value = e?.response?.data?.detail ?? e?.message ?? String(e) }
}

async function deactivate(g) {
  await deactivateGroup(g.id)
  await load()
}

async function reactivate(g) {
  await reactivateGroup(g.id)
  await load()
}

async function remove(g) {
  if (!confirm(`Delete group "${g.name}"?`)) return
  await deleteGroup(g.id)
  if (selected.value?.id === g.id) selected.value = null
  await load()
}

function openAddMember() {
  const existingIds = new Set((selected.value?.members ?? []).map(m => m.id))
  memberCandidates.value = allUsers.value.filter(u => !existingIds.has(u.id))
  Object.keys(candidateChecked).forEach(k => delete candidateChecked[k])
  leaderCandidateId.value = null
  memberError.value       = ''
  showAddMember.value     = true
}

function onCandidateChange(uid) {
  if (!candidateChecked[uid] && leaderCandidateId.value === uid) {
    leaderCandidateId.value = null
  }
}

async function saveMember() {
  memberError.value = ''
  const uids = memberCandidates.value.map(u => u.id).filter(id => candidateChecked[id])
  if (!uids.length) return
  try {
    await Promise.all(
      uids.map(uid =>
        addMember(selected.value.id, { user_id: uid, is_leader: leaderCandidateId.value === uid })
      )
    )
    showAddMember.value = false
    selected.value = await getGroup(selected.value.id)
  } catch (e) {
    memberError.value = e?.response?.data?.detail ?? e?.message ?? String(e)
  }
}

async function kickMember(member) {
  await removeMember(selected.value.id, member.id)
  selected.value = await getGroup(selected.value.id)
}
</script>

<style scoped>
.page     { padding: 24px; flex: 1; }
.clickable { cursor: pointer; }
.row-inactive td { opacity: 0.45; }
button.warning { background: rgba(234,179,8,.15); border-color: #ca8a04; color: #ca8a04; }
.actions  { display: flex; gap: 8px; }
.error    { color: var(--danger); font-size: 13px; margin-bottom: 8px; }
.color-swatch { padding: 2px 10px; border-radius: 4px; color: #fff; font-size: 12px; }
.color-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; }
.color-row { display: flex; gap: 8px; align-items: center; }
.color-picker { width: 40px; height: 36px; padding: 2px; border-radius: 6px; cursor: pointer; }
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,.6);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.modal {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 28px; width: 500px; max-height: 90vh; overflow-y: auto;
}

.member-add-row {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}
.member-select { flex: 1; }
.leader-check  { display: flex; align-items: center; gap: 4px; font-size: 12px; white-space: nowrap; color: var(--text-muted); cursor: pointer; }

.pending-member-list { display: flex; flex-direction: column; gap: 4px; }
.candidate-list { display: flex; flex-direction: column; gap: 4px; max-height: 280px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
.candidate-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.candidate-check { display: flex; align-items: center; gap: 6px; flex: 1; font-size: 13px; cursor: pointer; }
.no-candidates { font-size: 13px; color: var(--text-muted); }
.pending-member-row  { display: flex; align-items: center; gap: 8px; padding: 5px 8px; background: var(--bg-card); border-radius: 6px; }
.member-name { flex: 1; font-size: 13px; }
button.small { padding: 2px 7px; font-size: 12px; }
.leader-toggle {
  background: none; border: 1px solid var(--border); border-radius: 4px;
  padding: 1px 6px; font-size: 13px; color: var(--text-muted); cursor: pointer;
  transition: all .15s;
}
.leader-toggle.active { color: #ffc900; border-color: #ffc900; background: rgba(255,200,0,0.12); }
.leader-toggle:hover  { color: #ffc900; }
.modal h3 { margin-bottom: 20px; font-size: 16px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
</style>
