import { api } from './api'

export async function listTechs({ includeInactive = false } = {}) {
    return (await api.get(`/api/techs${includeInactive ? '?include_inactive=true' : ''}`)).techs
}