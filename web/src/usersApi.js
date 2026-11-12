import { api } from './api'

const base = '/api/admin/users'

export async function listUsers() {
    return (await api.get(base)).users
}

export async function createUser(data) {
    return (await api.post(base, data)).user
}

const act = async (id, suffix, body) => (await api.post(`${base}/${id}/${suffix}`, body)).user

export const deactivateUser = (id) => act(id, 'deactivate')
export const reactivateUser = (id) => act(id, 'reactivate')
export const unlockUser = (id) => act(id, 'unlock')
export const resetTotp = (id) => act(id, 'reset-totp')
export const resetPassword = (id, newPassword) => act(id, 'reset-password', { new_password: newPassword })