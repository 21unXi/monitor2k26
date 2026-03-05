# Steam价格监控项目概述

## 项目简介

这是一个用于监控Steam游戏价格的工具，能够定时获取游戏价格信息并在价格变动时发送通知。项目通过GitHub Actions定时运行，自动检测游戏价格变化并生成通知。

## 项目结构

```
monitor2k26/
├── .github/workflows/steam_price_monitor.yml  # GitHub Actions工作流配置
├── .gitignore                                # Git忽略文件
├── LICENSE                                   # 许可证文件
├── README.md                                 # 项目简介
├── PROJECT_OVERVIEW.md                       # 项目概述文档
├── monitor.py                                # 核心监控脚本
├── price_log.txt                             # 价格日志文件
├── requirements.txt                          # 依赖项配置
└── result.md                                 # 用于邮件通知的临时文件
```

## 核心功能

1. **价格获取**：通过Steam Store API获取指定游戏的价格信息，确保获取包含游戏本体的最低价格套餐
2. **价格比较**：与历史价格进行比较，检测价格变动
3. **通知生成**：当价格变动时生成通知内容
4. **日志记录**：记录价格历史，保持滚动日志
5. **套餐选择**：优先使用API返回的基础版价格（包含游戏本体），如果没有则从套餐组中选择包含游戏本体的最低价格套餐，包括同捆包在内的所有包含游戏本体的选择

## 配置方法

### 1. 依赖安装

```bash
pip install -r requirements.txt
```

### 2. 游戏配置

在`monitor.py`文件中修改`APP_IDS`列表，添加需要监控的游戏App ID：

```python
# 需要监控的游戏 App ID 列表
APP_IDS = [
    "3472040", # NBA 2K26
    "2828020", # Citystate Metropolis
    # 添加更多游戏App ID
]
```

### 3. GitHub Actions配置

项目已配置GitHub Actions工作流，默认每天运行一次。如需修改运行频率，可编辑`.github/workflows/steam_price_monitor.yml`文件。

## 使用示例

### 手动运行

```bash
python monitor.py
```

### 查看日志

价格历史记录保存在`price_log.txt`文件中，可通过查看该文件了解价格变化历史。

### 通知查看

当价格变动时，脚本会生成`result.md`文件，包含价格变动的详细信息。

## 技术依赖

- **Python 3.x**：主要开发语言
- **requests**：用于调用Steam Store API
- **GitHub Actions**：用于定时运行监控脚本

## 工作原理

1. **初始化**：脚本启动时，会获取当前时间并准备监控游戏列表
2. **价格获取**：对每个游戏调用Steam Store API获取价格信息，确保获取包含游戏本体的最低价格套餐
   - 优先使用API返回的`price_overview`（通常是基础版价格，包含游戏本体）
   - 如果没有`price_overview`，则从`package_groups`中选择包含游戏本体的最低价格套餐
   - 包括同捆包在内的所有包含游戏本体的选择，确保获取最优惠的价格
3. **价格比较**：与历史价格进行比较，检测是否发生变动
4. **通知生成**：如果价格变动，生成通知内容并写入`result.md`文件
5. **日志更新**：将当前价格信息添加到日志文件中

## 注意事项

- 脚本使用中国区价格（CNY），如需修改货币区域，可修改`get_game_price`函数中的`cc`参数
- 日志文件默认保留最近100行记录，可通过修改`MAX_LOG_LINES`变量调整
- 首次运行时，由于没有历史价格记录，不会发送通知

## 扩展建议

1. **添加更多游戏**：在`APP_IDS`列表中添加更多游戏App ID
2. **修改监控频率**：调整GitHub Actions工作流的运行频率
3. **添加邮件通知**：配置SMTP服务器，实现邮件通知功能
4. **添加Web界面**：创建简单的Web界面，展示价格历史和变动情况