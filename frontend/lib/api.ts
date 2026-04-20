import axios from 'axios'

// All requests go to /api/... which Next.js proxies to the backend (hamzabhatti-job-hunter.hf.space)
// This avoids all CORS issues — requests are same-origin from the browser's perspective
const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use(config => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
