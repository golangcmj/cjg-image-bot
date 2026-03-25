# 蠢酒馆生图

一个只保留核心能力的 AstrBot 生图插件。

这版只做一件事：

- 用户发送 `/生图 提示词`
- 插件先回复 `图片生成中`
- 生成完成后，引用回复用户原始命令消息并回图

不保留旧的手办化、改图、多 Key、文件转发、额外提示词包装等逻辑。

## 当前能力

- 只保留 `/生图`
- 后台固定一个 `preset-*` 模型 ID
- 运行时请求 `/v1/models` 校验模型是否可用
- 实际生图请求走 `/v1/images/generations`
- 请求体只发送 `model` 和 `prompt`
- 用户输入的空格、换行、段落都会原样保留
- 插件侧不设置生成总超时，慢图会一直等
- 如果后端返回的是 URL，会先下载图片，再作为图片发回去

## 配置项

插件后台只需要 3 个配置：

### `openai_api_base`

生图服务地址。

支持这两种写法：

- `https://your-host`
- `https://your-host/v1`

插件会自动拼接：

- `/v1/models`
- `/v1/images/generations`

### `openai_api_key`

你自己的 API Key。

### `selected_model_id`

固定模型 ID，必须填写你服务端返回的 `preset-*` 值，例如：

```text
preset-314
```

插件运行时会请求 `/v1/models` 检查这个模型是否还存在。

## 使用方式

### 命令

```text
/生图 二次元美女
```

也支持多行提示词：

```text
/生图
二次元美女

白色长发
蓝色眼睛
```

命令后的内容会原样作为 `prompt` 发送，不会额外拼接说明词。

## 请求格式

插件向后端发送的请求体固定为：

```json
{
  "model": "preset-314",
  "prompt": "用户原始输入"
}
```

不会发送：

- `size`
- `n`
- `quality`
- 其它多余字段

## 返回逻辑

后端返回后，插件按下面规则处理：

- 如果返回 `b64_json`，直接解码成图片
- 如果返回图片 URL，先下载图片字节
- 最终统一落盘成图片文件，再由 AstrBot 发图

最终结果会：

- 先发一条 `图片生成中`
- 出图后引用回复用户原始命令消息

## 项目结构

```text
.
├─ main.py
├─ metadata.yaml
├─ _conf_schema.json
├─ LICENSE
├─ README.md
├─ tests/
│  └─ test_ttp.py
└─ utils/
   ├─ image_core.py
   ├─ image_http.py
   └─ image_store.py
```

## 说明

这个仓库现在是精简版，只保留蠢酒馆生图需要的最小链路。
