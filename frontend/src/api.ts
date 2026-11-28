import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1',
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('pactelle_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('pactelle_token');
      localStorage.removeItem('pactelle_session');
      if (!['/login', '/register'].includes(window.location.pathname)) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export const message = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((item: { msg?: string }) => item.msg || 'Invalid request').join(', ');
    }
    return error.message || 'Request failed';
  }
  return error instanceof Error ? error.message : 'Request failed';
};

export const apiCall = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }).then((response) => response.data),

  register: (payload: object) =>
    api.post('/auth/register', payload).then((response) => response.data),

  dashboard: (organizationId: string) =>
    api.get(`/organizations/${organizationId}/dashboard`).then((response) => response.data),

  contracts: (organizationId: string) =>
    api.get(`/contracts/organizations/${organizationId}`).then((response) => response.data),

  createContract: (organizationId: string, payload: object) =>
    api.post(`/contracts/organizations/${organizationId}`, payload).then((response) => response.data),

  updateContract: (contractId: string, payload: object) =>
    api.patch(`/contracts/${contractId}`, payload).then((response) => response.data),

  upload: (contractId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`/documents/upload/${contractId}`, form).then((response) => response.data);
  },

  contractDocuments: (contractId: string) =>
    api.get(`/contracts/${contractId}/documents`).then((response) => response.data),

  process: (documentId: string) =>
    api.post(`/documents/${documentId}/process`).then((response) => response.data),

  processingStatus: (documentId: string) =>
    api.get(`/documents/${documentId}/processing-status`).then((response) => response.data),

  findings: (organizationId: string) =>
    api.get(`/organizations/${organizationId}/portfolio-findings`, {
      params: { page: 1, page_size: 100 },
    }).then((response) => response.data),

  finding: (organizationId: string, findingId: string) =>
    api.get(`/organizations/${organizationId}/portfolio-findings/${findingId}`).then((response) => response.data),

  analyse: (organizationId: string) =>
    api.post(`/organizations/${organizationId}/portfolio-analysis`).then((response) => response.data),

  findingStatus: (organizationId: string, findingId: string, status: string) =>
    api.patch(`/organizations/${organizationId}/portfolio-findings/${findingId}/status`, { status })
      .then((response) => response.data),

  recommendActions: (organizationId: string, findingId: string) =>
    api.post(`/organizations/${organizationId}/portfolio-findings/${findingId}/action-recommendations`)
      .then((response) => response.data),

  actions: (organizationId: string) =>
    api.get(`/organizations/${organizationId}/portfolio-actions`, {
      params: { page: 1, page_size: 100 },
    }).then((response) => response.data),

  createAction: (organizationId: string, payload: object) =>
    api.post(`/organizations/${organizationId}/portfolio-actions`, payload).then((response) => response.data),

  assignAction: (organizationId: string, actionId: string, userId: string | null) =>
    api.patch(`/organizations/${organizationId}/portfolio-actions/${actionId}/assignment`, {
      assigned_to_user_id: userId,
    }).then((response) => response.data),

  actionStatus: (organizationId: string, actionId: string, status: string, comment?: string) =>
    api.patch(`/organizations/${organizationId}/portfolio-actions/${actionId}/status`, {
      status,
      comment,
    }).then((response) => response.data),

  obligations: (organizationId: string) =>
    api.get(`/organizations/${organizationId}/obligations`, {
      params: { page: 1, page_size: 100 },
    }).then((response) => response.data),

  syncObligations: (organizationId: string) =>
    api.post(`/organizations/${organizationId}/obligations/sync`).then((response) => response.data),

  obligationStatus: (organizationId: string, obligationId: string, payload: object) =>
    api.patch(`/organizations/${organizationId}/obligations/${obligationId}`, payload)
      .then((response) => response.data),

  members: (organizationId: string) =>
    api.get(`/organizations/${organizationId}/members`).then((response) => response.data),

  inviteMember: (organizationId: string, payload: object) =>
    api.post(`/organizations/${organizationId}/members`, payload).then((response) => response.data),

  updateMemberRole: (organizationId: string, userId: string, role: string) =>
    api.patch(`/organizations/${organizationId}/members/${userId}/role`, { role })
      .then((response) => response.data),

  removeMember: (organizationId: string, userId: string) =>
    api.delete(`/organizations/${organizationId}/members/${userId}`).then((response) => response.data),
};
