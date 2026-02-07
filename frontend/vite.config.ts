import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// 读取 package.json 获取版本号
const packageJson = JSON.parse(
  readFileSync(resolve(__dirname, 'package.json'), 'utf-8')
)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // 定义全局常量，在构建时注入
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(packageJson.version),
    'import.meta.env.VITE_BUILD_TIME': JSON.stringify(
      new Date().toISOString().split('T')[0]
    ),
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // 手动分割代码块，将大型依赖库分离
        manualChunks: {
          // React 核心库
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          // Ant Design UI库（最大的依赖）
          'vendor-antd': ['antd', '@ant-design/icons'],
          // 其他工具库
          'vendor-utils': ['axios', 'dayjs', 'zustand'],
          // Diff查看器（较大的组件）
          'vendor-diff': ['react-diff-viewer-continued'],
          // 拖拽库
          'vendor-dnd': ['react-beautiful-dnd'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
