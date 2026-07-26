"""全项目共用的 LLM 配置。

为什么要抽出来(2026-07-26 的教训):DeepSeek 下线 deepseek-chat 那天,模型名硬编码在
26 处、15 个文件里,供应商单方面改个名字,全仓库都得改一遍。
模型名属于「外部依赖的标识符」——这类东西集中一处 + 环境变量覆盖,抽象成本几乎为零、
收益是确定的,不属于「为不会到来的未来过早抽象」。

换模型:改 .env 里的 LLM_MODEL 即可,代码一行不动。
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 当前可选:deepseek-v4-flash(快/便宜,确定性小任务够用) / deepseek-v4-pro(强/贵)
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
