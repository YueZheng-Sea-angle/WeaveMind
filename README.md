# ReadAgent

为长篇小说（10万字以上）构建的多 Agent 写作分析软件。

## 技术栈

- **前端**: React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui
- **后端**: Python 3.11 + FastAPI + SQLAlchemy 2.0 + ChromaDB
- **AI**: LangChain + LangGraph，支持 OpenAI / Anthropic，可在前端配置

## 快速开始

### 一键启动（推荐）

```bash
chmod +x start.sh
./start.sh
# 二次启动可跳过依赖安装（更快）
./start.sh --skip-install
```

说明：
- 脚本会自动创建后端虚拟环境并安装 `backend/requirements.txt`
- 首次运行会自动安装前端依赖（`frontend/node_modules`）
- 若依赖已安装，可用 `./start.sh --skip-install` 直接启动
- 启动后前端地址为 `http://127.0.0.1:5173`，后端地址为 `http://127.0.0.1:8000`
- 按 `Ctrl+C` 会同时关闭前后端

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填写 API Key
uvicorn main:app --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 项目结构

```
readagent/
├── frontend/       # React+Vite 前端
├── backend/        # FastAPI 后端
│   ├── app/
│   │   ├── api/        # 路由
│   │   ├── agents/     # Agent 实现
│   │   ├── models/     # SQLAlchemy ORM
│   │   ├── schemas/    # Pydantic 模型
│   │   ├── services/   # 业务逻辑
│   │   ├── tools/      # LangChain Tools
│   │   ├── db/         # 数据库 & ChromaDB
│   │   └── core/       # 配置
│   └── main.py
└── README.md
```
