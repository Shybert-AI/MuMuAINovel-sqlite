# MuMuAINovel-sqlite 📚✨

<div align="center">

![Version](https://img.shields.io/badge/version-1.3.3-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-green.svg)
![React](https://img.shields.io/badge/react-18.3.1-blue.svg)
![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)

**基于 AI 的智能小说创作助手**

[特性](#-特性) • [快速开始（本地 SQLite 部署）](#-快速开始本地-sqlite-部署) • [配置说明](#%EF%B8%8F-配置说明) • [项目结构](#-项目结构)

</div>

### 声明：感谢该官方的开源，https://github.com/xiamuceer-j/MuMuAINovel，本项目是移除docker安装，直接运行在windows环境。
## ✨ 特性

- 🤖 **多 AI 模型** - 支持 OpenAI、Gemini、Claude 等主流模型
- 📝 **智能向导** - AI 自动生成大纲、角色和世界观
- 👥 **角色管理** - 人物关系、组织架构可视化管理
- 📖 **章节编辑** - 支持创建、编辑、重新生成和润色
- 🌐 **世界观设定** - 构建完整的故事背景
- 🔐 **本地登录** - 本地账户登录，无需 OAuth
- 💾 **SQLite 数据库** - 轻量级本地数据库，无需 Docker
- 🖥️ **纯本地部署** - 无需容器，直接运行

## 📸 项目预览

<details>

<summary>多图预警</summary>

<div align="center">

### 登录界面
![登录界面](images/1.png)

### 主界面
![主界面](images/2.png)

### 项目管理
![项目管理](images/3.png)

### 赞助我 💖
![赞助我](images/4.png)

</div>

</details>

## 📋 TODO List

### ✅ 已完成功能

- [x] **灵感模式** - 创作灵感和点子生成
- [x] **自定义写作风格** - 支持自定义 AI 写作风格
- [x] **数据导入导出** - 项目数据的导入导出
- [x] **Prompt 调整界面** - 可视化编辑 Prompt 模板
- [x] **章节字数限制** - 用户可设置生成字数
- [x] **思维链与章节关系图谱** - 可视化章节逻辑关系
- [x] **根据分析一键重写** - 根据分析建议重新生成
- [x] **Linux DO 自动创建账号** - OAuth 登录自动生成账号
- [x] **职业等级体系** - 自定义职业和等级系统，支持修仙境界、魔法等级等多种体系
- [x] **角色/组织卡片导入导出** - 单独导出角色和组织卡片，支持跨项目数据共享
- [x] **伏笔管理** - 智能追踪剧情伏笔，提醒未回收线索，可视化伏笔时间线
- [x] **提示词工坊** - 社区驱动的 Prompt 模板分享平台，一键导入优质提示词
- [x] **章节标题** - 章节标题可以使用AI生成

![xiaoshuo.jpg](xiaoshuo.jpg)

> **📌 说明**
> - **Embedding 模型**：约 400 MB 磁盘空间，运行时加载到内存
> - 模型下载
modelscope download --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2  --local_dir ./dir
> - **SQLite 数据库**：自动创建，无需额外配置
> - 本项目主要依赖外部 AI API（OpenAI/Claude/Gemini），不需要本地 GPU

## 🚀 快速开始（本地 SQLite 部署）

### 前置要求

- **Python 3.11+**
- **Node.js 18+**（用于前端构建）
- 至少一个 AI 服务的 API Key（推荐使用 DeepSeek）

### 1. 克隆项目

```bash
git clone https://github.com/xiamuceer-j/MuMuAINovel.git
cd MuMuAINovel
```

### 2. 安装 Python 依赖

```bash
# 进入后端目录
cd backend

# 安装依赖（推荐使用虚拟环境）
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制环境变量示例文件
cp .env.example .env

# 编辑 .env 文件，配置以下关键项：
```

#### 关键配置项说明：

```ini
# AI 服务配置（必需）
OPENAI_API_KEY=sk-你的API密钥           # 例如 DeepSeek API Key
OPENAI_BASE_URL=https://api.deepseek.com  # DeepSeek API 地址

# 默认 AI 配置
DEFAULT_AI_PROVIDER=openai
DEFAULT_MODEL=deepseek-chat              # DeepSeek 模型
DEFAULT_TEMPERATURE=0.7
DEFAULT_MAX_TOKENS=8192                  # DeepSeek 模型限制为 8192 令牌

# 数据库配置（自动使用 SQLite）
# 无需设置 DATABASE_URL，系统会自动使用 SQLite
# 数据库文件将创建在：项目根目录/data/mumuai_novel.db

# 本地账户登录配置
LOCAL_AUTH_ENABLED=true
LOCAL_AUTH_USERNAME=admin
LOCAL_AUTH_PASSWORD=admin123
LOCAL_AUTH_DISPLAY_NAME=本地管理员
```

> **💡 提示**：如果没有 `.env` 文件，系统会自动创建 SQLite 数据库文件。
### 4_1 快捷启用方式：
```commandline
start.bat     #后端启动脚本
start_ui.bat  #前端启动脚本
```
### 4. 构建前端

```bash
# 返回项目根目录
cd ..

# 进入前端目录
cd frontend

# 安装前端依赖
npm install

# 构建前端静态文件
npm run build
```

### 5. 启动后端服务

```bash
# 返回项目根目录
cd ..

# 启动后端服务器（Windows）
start.bat

# 或者手动启动（Linux/macOS）
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. 访问应用

打开浏览器访问：http://localhost:8000

使用以下凭据登录：
- **用户名**: `admin`
- **密码**: `admin123`

## 📁 项目结构

```
MuMuAINovel/
├── backend/                    # 后端代码
│   ├── app/                   # 应用核心代码
│   │   ├── api/              # API 路由
│   │   ├── services/         # 业务服务
│   │   ├── models/           # 数据模型
│   │   └── database.py       # 数据库配置
│   ├── .env                  # 环境变量配置
│   ├── requirements.txt      # Python 依赖
│   └── main.py              # 应用入口
├── frontend/                 # 前端代码（React）
│   ├── public/              # 静态资源
│   ├── src/                 # 前端源代码
│   └── package.json         # 前端依赖
├── data/                    # SQLite 数据库文件（自动创建）
├── logs/                    # 日志文件（自动创建）
├── start.bat               # Windows 启动脚本
├── start.ps1               # PowerShell 启动脚本
└── README.md              # 英文文档
```

## 🔧 数据库说明

### SQLite 数据库

- **位置**: `data/mumuai_novel.db`
- **自动创建**: 首次启动时自动创建数据库和表结构
- **WAL 模式**: 启用 Write-Ahead Logging 模式，支持更好的并发性能
- **备份建议**: 定期备份 `data/` 目录

### 数据库初始化

如果数据库文件不存在，系统会自动：
1. 创建 `data/` 目录（如果不存在）
2. 初始化 SQLite 数据库
3. 创建所有必要的表结构
4. 创建默认管理员账户（如果配置了本地登录）

## 🤖 AI 模型支持

### 支持的 AI 提供商

| 提供商 | 模型示例 | 配置说明 |
|--------|----------|----------|
| **OpenAI** | gpt-4, gpt-4o-mini | 设置 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | 使用 `https://api.deepseek.com` 作为 `OPENAI_BASE_URL` |
| **Gemini** | gemini-pro | 设置 `GEMINI_API_KEY` |
| **Claude** | claude-3-opus | 设置 `ANTHROPIC_API_KEY` |

### DeepSeek 专用配置

```ini
# DeepSeek 配置示例
OPENAI_API_KEY=sk-你的DeepSeek密钥
OPENAI_BASE_URL=https://api.deepseek.com
DEFAULT_MODEL=deepseek-chat
DEFAULT_MAX_TOKENS=8192  # DeepSeek 模型最大限制
```

> **⚠️ 注意**: DeepSeek 模型有 8192 令牌限制，超过会自动调整为 8192。

## 🐛 常见问题

### Q1: 启动时提示端口被占用？
**A**: 修改 `.env` 文件中的 `APP_PORT` 为其他端口（如 8001），或关闭占用 8000 端口的程序。

### Q2: 数据库文件在哪里？
**A**: 在 `项目根目录/data/mumuai_novel.db`。首次启动时自动创建。

### Q3: 如何重置管理员密码？
**A**: 删除数据库文件 `data/mumuai_novel.db` 并重启服务，系统会重新创建默认账户。

### Q4: 前端构建失败？
**A**: 确保 Node.js 版本 ≥ 18，并尝试：
```bash
cd frontend
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Q5: API 调用返回 402 错误？
**A**: 检查 API 密钥余额是否充足，或确认 API 服务配置正确。

### Q6: 如何启用 PostgreSQL 数据库？
**A**: 在 `.env` 文件中设置 `DATABASE_URL` 为 PostgreSQL 连接字符串，例如：
```ini
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/mumuai_novel
```

## 🔄 更新项目

```bash
# 拉取最新代码
git pull origin main

# 更新后端依赖
cd backend
pip install -r requirements.txt --upgrade

# 更新前端依赖并重新构建
cd ../frontend
npm install
npm run dev
npm run build
```

## 📄 许可证

本项目采用 **GPL v3** 许可证。详见 [LICENSE](LICENSE) 文件。

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！贡献前请阅读：
1. 提交 Issue 时请描述清晰的问题或需求
2. Pull Request 请基于 `main` 分支
3. 确保代码风格与项目一致
4. 更新相关文档

## 📞 联系方式


- **QQ 群**: 1029629549

---

<div align="center">

**享受 AI 辅助的小说创作之旅吧！** ✨

如果觉得项目有用，别忘了点个 ⭐ Star 支持！

</div>

[![Star History Chart](https://api.star-history.com/svg?repos=Shybert-AI/MuMuAINovel-sqlite&type=Date)](https://star-history.com/#Shybert-AI/MuMuAINovel-sqlite&Date)
