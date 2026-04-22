# ReadAgent

为长篇小说（10万字以上）构建的多 Agent 写作分析软件。

## 技术栈

- **前端**: React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui
- **后端**: Python 3.11 + FastAPI + SQLAlchemy 2.0 + ChromaDB
- **AI**: LangChain + LangGraph，支持 OpenAI / Anthropic，可在前端配置

## 快速开始

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
