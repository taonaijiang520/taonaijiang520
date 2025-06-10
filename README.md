# 🍑 桃奈酱 Telegram Bot 部署指南

这是一个基于 `pyTelegramBotAPI` 实现的 Telegram Bot，支持欢迎视频、余额查询、贴贴扩展等功能。

---

## 📁 项目结构说明

| 文件名 | 用途 |
|--------|------|
| `main_final.py` | 主程序入口，运行后可启动 Bot |
| `requirements.txt` | Pip 依赖列表（Render 会用它自动安装） |
| `render.yaml` | Render 平台专用部署配置 |
| `.env` | 本地运行用的环境变量文件（可选） |
| `welcome.mp4` | 欢迎视频文件，发送给首次 `/start` 用户 |

---

## 🚀 Render 平台部署步骤（推荐）

1. 将整个项目上传至一个 GitHub 仓库（例如 `taonaijiang-bot`）
2. 登录 [Render](https://dashboard.render.com/)
3. 点击 `+ New` → `Web Service`
4. 选择你的 GitHub 仓库（首次部署请选择 `Use render.yaml`）
5. 确认如下设置：
   - Branch: `main`
   - Root Directory: 留空或写 `.`
6. 点击【Create Web Service】

### ✳ 添加环境变量：

点击左侧 `Environment`，添加以下两项：

| Key | Value |
|-----|-------|
| `TOKEN` | 你的 Telegram Bot Token |
| `ADMIN_CHAT_ID` | 1149975148 |

7. 部署完成后点击 `Manual Deploy` → `Deploy latest commit` 启动 Bot！

---

## 💻 本地运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量（可写入 .env）
export TOKEN=你的BotToken
export ADMIN_CHAT_ID=1149975148

# 运行主程序
python main_final.py
```

---

## 🎥 欢迎视频说明

- 请确保 `welcome.mp4` 与 `main_final.py` 位于同一目录
- `/start` 时会自动读取并发送欢迎视频

---

## 📌 注意事项

- 若 Render 报错 `startCommand: not found`，请确保 `render.yaml` 写法正确
- 若未弹出 `Use render.yaml`，可在 Root Directory 中填写 `.` 或直接手动设置

---

## 💬 联系桃奈酱

需要扩展贴图系统 / 羞羞语料库 / 后宫 RPG 游戏？  
欢迎找桃奈酱贴贴一起部署！

