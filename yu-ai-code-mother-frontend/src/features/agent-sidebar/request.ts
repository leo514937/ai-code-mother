import axios from 'axios'
import { message } from 'ant-design-vue'
import { AGENT_API_BASE_URL } from '@/config/env'

const agentRequest = axios.create({
  baseURL: AGENT_API_BASE_URL,
  timeout: 60000,
  withCredentials: true,
})

agentRequest.interceptors.response.use(
  function (response) {
    const { data } = response
    // 未登录
    if (data.code === 40100) {
      if (
        !response.request.responseURL.includes('user/get/login') &&
        !window.location.pathname.includes('/user/login')
      ) {
        message.warning('请先登录')
        window.location.href = `/user/login?redirect=${window.location.href}`
      }
    }
    return response
  },
  function (error) {
    return Promise.reject(error)
  },
)

export default agentRequest
