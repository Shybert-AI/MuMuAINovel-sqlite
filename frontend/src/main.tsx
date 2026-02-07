import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import 'antd/dist/reset.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#4D8088', // 天青
          colorBgBase: '#F8F6F1', // 米汤色
          colorTextBase: '#2B2B2B', // 墨色
          borderRadius: 6,
          wireframe: false,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif",
        },
        components: {
          Layout: {
            bodyBg: '#F8F6F1',
            headerBg: '#FFFFFF',
            siderBg: '#FFFFFF',
          },
          Card: {
            colorBgContainer: '#FFFFFF',
            boxShadowTertiary: '0 4px 12px rgba(0, 0, 0, 0.05)', // 更柔和的阴影
          },
          Button: {
            borderRadius: 6,
            controlHeight: 36,
          }
        }
      }}
    >
      <App />
    </ConfigProvider>
  </StrictMode>,
)
